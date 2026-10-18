import json
import unittest

from breakpoint.codeindex import CodeIndex
from breakpoint.routemap import _scrub, map_routes, render

from tests.test_codeindex import make_repo

SERVER = '''const express = require("express");
const bodyParser = require("body-parser");
const apiRouter = require("./routes/api");
const routes = require("./routes");
const app = express();
// app.use(csrf());
app.use(bodyParser.json());
app.use("/api", apiRouter);
routes(app, db);
app.listen(3000);
'''

INDEX = '''const Handler = require("./handler");
module.exports = (app, db) => {
    const h = new Handler(db);
    const isLoggedIn = h.isLoggedIn;
    const isAdmin = h.isAdmin;
    app.get("/a", isLoggedIn, cors, h.show);
    app.post("/a", isLoggedIn, passport.authenticate("x"), h.save);
    /*
    app.post("/a", isLoggedIn, isAdmin, h.save);
    */
    app.get("/go", (req, res) => {
        return res.redirect(req.query.url);
    });
    app.get("port");
};
'''

HANDLER = '''const Dao = require("../data/dao").Dao;
function Handler(db) {
    const dao = new Dao(db);
    this.isLoggedIn = (req, res, next) => { return req.session.id ? next() : res.redirect("/login"); };
    this.isAdmin = (req, res, next) => next();
    this.show = (req, res) => {
        const label = "a closing brace } inside a string, and an opening { too";  // { not code
        /* } nor this one { */
        dao.fetch(req.params.id, (err, row) => res.render("show", row));
    };
    this.save = (req, res) => {
        const n = eval(req.body.n);
        return res.send("ok");
    };
}
module.exports = Handler;
'''

DAO = '''const Dao = function (db) {
    this.fetch = (id, cb) => {
        db.find({ $where: "this.id == " + id }).toArray(cb);
    };
};
exports.Dao = Dao;
'''

API = '''const express = require("express");
const router = express.Router();
router.get("/ping", (req, res) => res.send("ok"));
module.exports = router;
'''

APP = {
    "server.js": SERVER, "routes/index.js": INDEX, "routes/handler.js": HANDLER, "data/dao.js": DAO,
    "routes/api.js": API,
    "test/server.test.js": 'const app = require("express")();\napp.get("/only-in-tests", (req, res) => res.send("x"));\n',
}


def build():
    idx = CodeIndex.from_dir(make_repo(APP))
    return idx, map_routes(idx)


def by_label(rm, label):
    return next(r for r in rm.routes if r.label == label)


class ScrubbingJavaScript(unittest.TestCase):
    def test_comments_and_string_contents_are_blanked_but_offsets_and_lines_survive(self):
        text = 'a("}{") // x {\n/* {\n} */ b(/[}"]/, "it\'s");\n'
        nc, sk = _scrub(text)
        self.assertEqual(len(nc), len(text))
        self.assertEqual(len(sk), len(text))
        self.assertEqual(nc.count("\n"), text.count("\n"))
        self.assertNotIn("x {", nc)
        self.assertIn('"}{"', nc)                      # strings stay readable in the comment-free view
        self.assertNotIn("}{", sk)                     # but not in the skeleton used to match brackets
        self.assertEqual(sk.count("{"), 0)             # braces in comments, strings and regex literals are all gone
        self.assertEqual(sk.count("}"), 0)


class MappingAnExpressApp(unittest.TestCase):
    def test_finds_exactly_the_real_routes(self):
        _, rm = build()
        self.assertEqual(rm.framework, "express")
        self.assertEqual(rm.entry_file, "server.js")
        self.assertEqual(sorted(r.label for r in rm.routes), ["GET /a", "GET /api/ping", "GET /go", "POST /a"])
        # `app.get("port")` reads a setting, a test file is not the app
        self.assertNotIn("GET port", [r.label for r in rm.routes])
        self.assertNotIn("GET /only-in-tests", [r.label for r in rm.routes])

    def test_follows_protections_and_handler_to_their_definitions(self):
        _, rm = build()
        r = by_label(rm, "GET /a")
        self.assertEqual([m["name"] for m in r.middleware], ["isLoggedIn", "cors"])
        guard = r.middleware[0]["span"]
        self.assertEqual((guard.file, guard.start), ("routes/handler.js", 4))
        self.assertIsNone(r.middleware[1]["span"])             # `cors` is not defined in this repo
        self.assertIn("cors", rm.unresolved)
        h = r.handler["span"]
        self.assertEqual(h.file, "routes/handler.js")
        self.assertEqual((h.start, h.end), (6, 10))            # braces inside strings and comments did not move the end

    def test_follows_the_handler_into_the_code_it_calls(self):
        _, rm = build()
        r = by_label(rm, "GET /a")
        self.assertEqual([(c.name, c.file, c.start, c.end) for c in r.callees], [("dao.fetch", "data/dao.js", 2, 4)])
        self.assertNotIn("http_request", r.sinks)      # `dao.fetch(` is a method, not the global fetch()
        self.assertIn("db_query", r.sinks)
        self.assertTrue(r.reads_input)

    def test_inline_handlers_and_dangerous_operations(self):
        _, rm = build()
        go = by_label(rm, "GET /go")
        self.assertEqual(go.handler["name"], "<inline>")
        self.assertEqual((go.handler["span"].start, go.handler["span"].end), (11, 13))
        self.assertIn("redirect", go.sinks)
        self.assertTrue(go.reads_input)
        self.assertIn("eval", by_label(rm, "POST /a").sinks)

    def test_a_protection_that_was_switched_off_is_reported(self):
        _, rm = build()
        post = by_label(rm, "POST /a")
        self.assertEqual(len(post.disabled_variants), 1)
        self.assertIn("isAdmin", post.disabled_variants[0]["text"])
        self.assertEqual(by_label(rm, "GET /a").disabled_variants, [])
        off = [g for g in rm.global_middleware if not g["active"]]
        self.assertEqual([g["expr"] for g in off], ["csrf()"])
        self.assertIn("bodyParser.json()", [g["expr"] for g in rm.global_middleware if g["active"]])

    def test_router_mounts_add_their_prefix(self):
        _, rm = build()
        ping = by_label(rm, "GET /api/ping")
        self.assertEqual(ping.file, "routes/api.js")

    def test_node_source_shows_the_code_a_reviewer_needs_with_line_numbers(self):
        idx, rm = build()
        post = by_label(rm, "POST /a")
        text = rm.node_source(post, idx)
        for needle in ("app.post", "isAdmin", "eval(req.body.n)", "req.session.id"):
            self.assertIn(needle, text)
        self.assertIn("c|", text)                               # the switched-off copy is marked as a comment
        self.assertNotIn("this.fetch", text)                    # the other route's callee is not dragged in

    def test_the_map_serialises(self):
        _, rm = build()
        data = json.loads(json.dumps(rm.to_dict()))
        self.assertEqual(len(data["routes"]), 4)
        self.assertIn("GET    /a", render(rm))


TS_APP = {
    "server.ts": ("import * as security from './lib/security'\nimport { login } from './routes/login'\n"
                  "import * as utils from './lib/utils'\nimport { upload } from './routes/upload'\n"
                  "const app = express()\napp.post('/rest/login', login())\napp.get('/api/Users', security.isAuthorized())\n"
                  "app.post('/upload', utils.asyncHandler(upload()))\napp.listen(3000)\n"),
    "lib/security.ts": "export const isAuthorized = () => expressJwt({ secret: 'k' })\n",
    "lib/utils.ts": "export const asyncHandler = (fn: any) => (req: any, res: any, next: any) => Promise.resolve(fn(req, res, next)).catch(next)\n",
    "routes/login.ts": ("export function login () {\n  return (req: any, res: any, next: any) => {\n"
                        "    db.query(`SELECT * FROM Users WHERE email = '${req.body.email}'`)\n  }\n}\n"),
    "routes/upload.ts": "export function upload () {\n  return async (req: any, res: any) => {\n    res.send(req.body)\n  }\n}\n",
}


class FactoryStyleHandlers(unittest.TestCase):
    """TypeScript apps often register `login()` or `asyncHandler(upload())`: a function that RETURNS the handler."""

    def setUp(self):
        self.rm = map_routes(CodeIndex.from_dir(make_repo(TS_APP)))

    def test_a_factory_call_resolves_to_the_function_that_builds_the_handler(self):
        r = by_label(self.rm, "POST /rest/login")
        self.assertEqual((r.handler["span"].file, r.handler["span"].start, r.handler["span"].end), ("routes/login.ts", 1, 5))
        self.assertTrue(r.reads_input)
        self.assertIn("db_query", r.sinks)

    def test_a_wrapper_is_skipped_in_favour_of_the_handler_it_wraps(self):
        r = by_label(self.rm, "POST /upload")
        self.assertEqual(r.handler["span"].file, "routes/upload.ts")             # not lib/utils.ts, the wrapper

    def test_a_namespace_import_is_followed(self):
        r = by_label(self.rm, "GET /api/Users")
        self.assertEqual(r.handler["span"].file, "lib/security.ts")


class WhenThereIsNothingToMap(unittest.TestCase):
    def test_a_repo_without_express_returns_an_empty_map_not_invented_routes(self):
        idx = CodeIndex.from_dir(make_repo({"app.py": "from flask import Flask\napp = Flask(__name__)\n@app.get('/x')\ndef x(): pass\n"}))
        rm = map_routes(idx)
        self.assertIsNone(rm.framework)
        self.assertEqual(rm.routes, [])
        self.assertIn("No Express app", render(rm))


if __name__ == "__main__":
    unittest.main()
