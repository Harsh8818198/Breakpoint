import os
import tempfile
import unittest
from pathlib import Path

from breakpoint.codeindex import CodeIndex, is_secret_file, redact_text


def make_repo(files: dict[str, str]) -> str:
    root = tempfile.mkdtemp(prefix="bp_test_repo_")
    for rel, text in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    return root


class SecretsStayOut(unittest.TestCase):
    def test_secret_files_are_never_indexed_but_templates_are(self):
        root = make_repo({
            ".env": "OPENAI_API_KEY=sk-live-abcdefghijklmnopqrstuvwx\n",
            ".env.production": "X=1\n", "deploy/server.pem": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
            "keys/prod-signing-key.hex": "deadbeef", ".env.example": "OPENAI_API_KEY=\n", "app.py": "print('hi')\n",
        })
        idx = CodeIndex.from_dir(root)
        self.assertEqual(sorted(idx.paths()), [".env.example", "app.py"])
        self.assertEqual(idx.skipped["secret"], 4)

    def test_is_secret_file(self):
        for n in (".env", ".env.local", "id_rsa", "cert.pem", "credentials.json", "prod-signing-key.hex"):
            self.assertTrue(is_secret_file(n), n)
        for n in (".env.example", "auth.py", "keyboard.py", "README.md"):
            self.assertFalse(is_secret_file(n), n)

    def test_secret_values_are_redacted_but_readable_constants_are_not(self):
        text = ('API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"\n'
                'password = "hunter2hunter2x9"\n'
                'KEYRING_USER = "google_refresh_token"\n'
                'data["token_in_keyring"] = True\n'
                'aws = "AKIAABCDEFGHIJKLMNOP"\n')
        out = redact_text(text)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", out)
        self.assertNotIn("hunter2hunter2x9", out)
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", out)
        self.assertIn("google_refresh_token", out)
        self.assertIn("token_in_keyring", out)

    def test_private_key_blocks_are_redacted_without_shifting_line_numbers(self):
        text = "a = 1\n-----BEGIN RSA PRIVATE KEY-----\nAAAA\nBBBB\n-----END RSA PRIVATE KEY-----\nstate_check = True\n"
        out = redact_text(text)
        self.assertEqual(out.count("\n"), text.count("\n"))
        self.assertNotIn("AAAA", out)
        self.assertEqual(out.splitlines()[5], "state_check = True")

    def test_redacted_text_is_what_gets_indexed(self):
        root = make_repo({"cfg.py": 'token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"\n'})
        idx = CodeIndex.from_dir(root)
        self.assertNotIn("ghp_", "\n".join(idx.lines("cfg.py")))


class WalkingTheRepo(unittest.TestCase):
    def test_skips_vendor_binary_and_huge_files(self):
        root = make_repo({
            "src/a.py": "x = 1\n", "node_modules/pkg/index.js": "evil()\n", ".git/config": "[core]\n",
            "logo.png": b"\x89PNG\r\n\x1a\n", "blob.dat": b"abc\x00def", "big.js": "x" * 400_000,
            "package-lock.json": "{}",
        })
        idx = CodeIndex.from_dir(root)
        self.assertEqual(idx.paths(), ["src/a.py"])

    def test_not_a_directory_raises(self):
        with self.assertRaises(ValueError):
            CodeIndex.from_dir(os.path.join(tempfile.gettempdir(), "definitely_missing_bp_dir"))


class ResolvingPaths(unittest.TestCase):
    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo({
            "consiz/auth.py": "a\n", "server/app.py": "b\n", "consiz/app.py": "c\n", ".github/workflows/ci.yml": "d\n"}))

    def test_exact_suffix_and_unique_basename(self):
        self.assertEqual(self.idx.resolve_path("consiz/auth.py"), "consiz/auth.py")
        self.assertEqual(self.idx.resolve_path("./consiz/auth.py"), "consiz/auth.py")
        self.assertEqual(self.idx.resolve_path("auth.py"), "consiz/auth.py")
        self.assertEqual(self.idx.resolve_path("consiz\\auth.py"), "consiz/auth.py")
        self.assertEqual(self.idx.resolve_path(".github/workflows/ci.yml"), ".github/workflows/ci.yml")

    def test_ambiguous_missing_and_traversal_are_rejected(self):
        self.assertIsNone(self.idx.resolve_path("app.py"))            # two files share that name
        self.assertIsNone(self.idx.resolve_path("nope.py"))
        self.assertIsNone(self.idx.resolve_path("../../etc/passwd"))
        self.assertIsNone(self.idx.resolve_path(None))                # type: ignore[arg-type]


class QuotesMustBeReal(unittest.TestCase):
    CODE = ("def callback(request):\n"
            "    code = request.args['code']\n"
            "    if request.args.get('state') != session['state']:\n"
            "        raise AuthError('bad state')\n"
            "    return exchange(code)\n"
            "\n"
            "def other():\n"
            "    if request.args.get('state') != session['state']:\n"
            "        pass\n")

    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo({"auth.py": self.CODE}))

    def test_exact_quote_gives_its_real_line(self):
        self.assertEqual(self.idx.find_quote("auth.py", "raise AuthError('bad state')"), 4)

    def test_whitespace_and_line_breaks_do_not_matter(self):
        self.assertEqual(self.idx.find_quote("auth.py", "if request.args.get('state')   !=\n   session['state']:", near=3), 3)

    def test_the_line_number_gutter_is_ignored(self):
        self.assertEqual(self.idx.find_quote("auth.py", "    3|     if request.args.get('state') != session['state']:", near=3), 3)

    def test_nearest_occurrence_wins(self):
        q = "if request.args.get('state') != session['state']:"
        self.assertEqual(self.idx.find_quote("auth.py", q, near=8), 8)
        self.assertEqual(self.idx.find_quote("auth.py", q, near=2), 3)

    def test_invented_or_trivial_quotes_are_rejected(self):
        self.assertIsNone(self.idx.find_quote("auth.py", "if not verify_state(request): abort(403)"))
        self.assertIsNone(self.idx.find_quote("auth.py", "return"))     # too short to prove anything
        self.assertIsNone(self.idx.find_quote("auth.py", ""))
        self.assertIsNone(self.idx.find_quote("missing.py", "raise AuthError('bad state')"))


class Searching(unittest.TestCase):
    def test_rare_terms_outrank_common_ones_and_preferred_files_come_first(self):
        files = {f"m{i}.py": "import os\nvalidate(x)\n" for i in range(12)}
        files["auth.py"] = "import os\ndef refresh_token_flow(): pass\n"
        idx = CodeIndex.from_dir(make_repo(files))
        ranked = idx.rank_files(["validate", "refresh_token_flow"], limit=3)
        self.assertEqual(ranked[0][0], "auth.py")
        self.assertEqual(ranked[0][1], [2])
        self.assertEqual(idx.rank_files([], preferred=["m3.py"], limit=1)[0][0], "m3.py")

    def test_big_files_are_shown_as_windows_with_true_line_numbers(self):
        body = "\n".join(f"line_{i} = {i}" for i in range(1, 3001))
        idx = CodeIndex.from_dir(make_repo({"big.py": body}))
        text = idx.excerpt("big.py", [2000])
        self.assertIn(" 2000| line_2000 = 2000", text)
        self.assertNotIn("line_1500 =", text)
        self.assertIn("   1| line_1 = 1", text)


if __name__ == "__main__":
    unittest.main()


class FollowingCalls(unittest.TestCase):
    def test_a_call_site_leads_to_the_callee_and_the_callees_callee(self):
        idx = CodeIndex.from_dir(make_repo({
            "router.py": "def process(ctx):\n    return Result(stream=llm.stream(ctx))\n",
            "llm.py": "def stream(ctx):\n    return _guard(_open(ctx))\n\ndef _guard(src):\n    yield from src\n\n"
                      "def _open(ctx):\n    with SESSION.post(url) as r:\n        yield r.text\n",
            "other.py": "def helper(): pass\n"}))
        hits = idx.callee_hits(["return Result(stream=llm.stream(ctx))"])
        self.assertIn("llm.py", hits)
        self.assertIn(1, hits["llm.py"])             # stream()
        self.assertIn(7, hits["llm.py"])             # two hops down: _open(), where the connection is opened and closed
        self.assertNotIn("other.py", hits)

    def test_library_and_overly_generic_names_are_not_followed(self):
        files = {f"m{i}.py": "def run(x):\n    pass\n" for i in range(5)}
        files["main.py"] = "def go():\n    requests.post(url)\n    run(1)\n"
        idx = CodeIndex.from_dir(make_repo(files))
        self.assertEqual(idx.callee_hits(["requests.post(url)", "run(1)"]), {})

    def test_js_and_go_definitions_are_found(self):
        idx = CodeIndex.from_dir(make_repo({
            "a.js": "export async function loadUser(id) {\n  return 1\n}\nconst parseBody = async (req) => {\n}\n",
            "b.go": "func (s *Server) handleLogin(w http.ResponseWriter) {\n}\n"}))
        self.assertEqual(idx.find_definitions("loadUser"), [("a.js", 1)])
        self.assertEqual(idx.find_definitions("parseBody"), [("a.js", 4)])
        self.assertEqual(idx.find_definitions("handleLogin"), [("b.go", 1)])


class QuotesModelsActuallyWrite(unittest.TestCase):
    JS = ("app.get('/learn', isLoggedIn, (req, res) => {\n"
          "    // Insecure way to handle redirects by taking redirect url from query string\n"
          "    return res.redirect(req.query.url);\n"
          "});\n")

    def setUp(self):
        filler = "".join(f"call_{i}(argument_{i}, other_{i});\n" for i in range(60))
        self.idx = CodeIndex.from_dir(make_repo({"routes.js": self.JS + filler + "app.get('/other', (req, res) => { res.send('x'); });\n"}))

    def test_comment_lines_between_copied_lines_may_be_left_out(self):
        q = "app.get('/learn', isLoggedIn, (req, res) => { return res.redirect(req.query.url); });"
        self.assertEqual(self.idx.find_quote("routes.js", q), 1)

    def test_an_ellipsis_joins_pieces_of_a_quote(self):
        self.assertEqual(self.idx.find_quote("routes.js", "app.get('/learn', isLoggedIn ... return res.redirect(req.query.url)"), 1)
        self.assertEqual(self.idx.find_quote("routes.js", "app.get('/learn', isLoggedIn \u2026 return res.redirect(req.query.url)"), 1)

    def test_pieces_must_be_in_order_and_close_together(self):
        self.assertIsNone(self.idx.find_quote("routes.js", "return res.redirect(req.query.url) ... app.get('/learn', isLoggedIn"))
        self.assertIsNone(self.idx.find_quote("routes.js", "app.get('/learn', isLoggedIn ... res.send('x')"))      # same file, but far apart
        self.assertIsNone(self.idx.find_quote("routes.js", "app.get('/learn', isLoggedIn ... a line that is not there at all"))

    def test_a_quote_of_only_a_comment_is_found_but_flagged_as_comment(self):
        q = "// Insecure way to handle redirects by taking redirect url from query string"
        line = self.idx.find_quote("routes.js", q)
        self.assertEqual(line, 2)
        self.assertTrue(self.idx.span_is_comment("routes.js", line, q))


class CommentDetection(unittest.TestCase):
    def test_masks_by_language(self):
        from breakpoint.codeindex import comment_mask
        js = ["a();", "// x", "/* start", "still", "end */", "b(); // trailing", "  * not in block"]
        self.assertEqual(comment_mask("a.js", js), [False, True, True, True, True, False, False])
        py = ["x = 1", "# note", "y = 2  # trailing"]
        self.assertEqual(comment_mask("a.py", py), [False, True, False])
        html = ["<p>", "<!-- one -->", "<!-- two", "more -->", "<b>"]
        self.assertEqual(comment_mask("a.html", html), [False, True, True, True, False])
        self.assertEqual(comment_mask("a.unknown", ["// x"]), [False])


class BlankAndCommentLinesInsideAQuote(unittest.TestCase):
    def test_a_quote_that_skips_blank_lines_and_a_commented_out_block_still_matches(self):
        code = ("app.use(session({\n"
                "    secret: cookieSecret,\n"
                "    resave: true\n"
                "    /*\n"
                "    cookie: { httpOnly: true }\n"
                "    */\n"
                "\n"
                "}));\n")
        idx = CodeIndex.from_dir(make_repo({"server.js": code}))
        self.assertEqual(idx.find_quote("server.js", "app.use(session({\n    secret: cookieSecret,\n    resave: true\n\n}));"), 1)
        # ...but the commented-out cookie options are not live code
        q = "cookie: { httpOnly: true }"
        self.assertTrue(idx.span_is_comment("server.js", idx.find_quote("server.js", q), q))


class DirectoriesNamedEnv(unittest.TestCase):
    def test_config_env_is_source_but_a_virtualenv_is_not(self):
        idx = CodeIndex.from_dir(make_repo({
            "config/env/all.js": "module.exports = { a: 1 };\n",
            "env/pyvenv.cfg": "home = /usr\n", "env/lib/site.py": "x = 1\n", "app.py": "y = 2\n"}))
        self.assertEqual(sorted(idx.paths()), ["app.py", "config/env/all.js"])
