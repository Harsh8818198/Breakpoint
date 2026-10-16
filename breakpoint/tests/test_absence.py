"""Claims that a protection is MISSING or SWITCHED OFF cannot be proved by quoting a live line, because there is none.
The verifier proves them by search instead: no live code uses the names the protection would carry, and the
commented-out copies the search finds are the evidence."""

import unittest

from breakpoint.codeindex import CodeIndex
from breakpoint.codeverify import CONFIRMED, REFUTED, UNVERIFIED, CodeVerifier

from tests.test_codeindex import make_repo
from tests.test_codeverify import ScriptedLLM, ev, finding, locate

SERVER = '''const express = require("express");
const session = require("express-session");
// const csrf = require("csurf");
const bcrypt = require("bcrypt-nodejs");
const insecureMode = true;
const app = express();
app.use(session({
    secret: cookieSecret,
    resave: true
    /*
    cookie: {
        httpOnly: true
        // secure: true
    }
    */
}));
// app.use(csrf());
// user.password = bcrypt.hashSync(password);
module.exports = app;
'''

REPO = {
    "server.js": SERVER,
    "README.md": "Remember to turn on helmet and httpOnly cookies before production.\n",
    "test/server.test.js": "// helmet is mocked here\nconst csrf = require('csurf'); csrf();\n",
    "package.json": '{"dependencies": {"helmet": "^3.0.0", "csurf": "^1.0.0"}}\n',
}


def line_of(text: str, needle: str) -> int:
    return next(i for i, ln in enumerate(text.splitlines(), 1) if needle in ln)


def absent_reply(names, evidence=(), impact=True, verdict="CONFIRMED"):
    return {"verdict": verdict, "impact_follows": impact, "reasoning": "the protection is commented out",
            "evidence": list(evidence), "absent_names": names}


class MissingProtections(unittest.TestCase):
    def check(self, names, files=None, evidence=(), impact=True, defend=None, title="Session cookies lack httpOnly"):
        idx = CodeIndex.from_dir(make_repo(files or REPO))
        llm = ScriptedLLM(verify_locate=locate(["server.js"], names or ["x"]),
                          verify_judge=absent_reply(names, evidence, impact),
                          verify_defend=defend or {"defence_found": False, "reasoning": "none", "evidence": []})
        return CodeVerifier(idx, llm).check(finding(title))

    def test_a_switched_off_protection_is_proved_by_search_and_the_commented_lines_are_the_evidence(self):
        r = self.check(["httpOnly"])
        self.assertEqual((r["status"], r["code"]), (CONFIRMED, "confirmed_absent"))
        self.assertEqual(r["evidence"], [{"file": "server.js", "line": line_of(SERVER, "httpOnly: true"),
                                          "quote": "httpOnly: true", "kind": "switched_off", "absent": "httpOnly"}])
        self.assertIn("No live code uses `httpOnly`", r["reasoning"])

    def test_the_judges_own_quote_is_not_needed_and_an_invented_one_does_not_get_in_the_way(self):
        r = self.check(["httpOnly"], evidence=[ev("server.js", "cookie: { httpOnly: true, secure: true } // paraphrased")])
        self.assertEqual((r["status"], r["code"]), (CONFIRMED, "confirmed_absent"))

    def test_a_real_live_quote_from_the_judge_still_wins(self):
        r = self.check(["httpOnly"], evidence=[ev("server.js", "secret: cookieSecret,")])
        self.assertEqual((r["status"], r["code"]), (CONFIRMED, "confirmed"))
        self.assertNotIn("kind", r["evidence"][0])

    def test_live_code_that_uses_the_name_means_absence_is_not_accepted(self):
        files = dict(REPO)
        files["lib/protect.js"] = "module.exports = (app) => app.use(csrf());\n"
        r = self.check(["csrf"], files=files, title="No CSRF protection")
        self.assertEqual(r["status"], UNVERIFIED)

    def test_a_bare_import_is_not_a_use_but_a_call_is(self):
        r = self.check(["bcrypt"], title="Passwords are stored in plain text")
        self.assertEqual((r["status"], r["code"]), (CONFIRMED, "confirmed_absent"))     # only `const bcrypt = require(...)` is live
        files = dict(REPO)
        files["server.js"] = SERVER.replace("module.exports = app;", "module.exports = app;\nconst h = bcrypt(password);")
        self.assertEqual(self.check(["bcrypt"], files=files)["status"], UNVERIFIED)

    def test_a_name_that_appears_nowhere_gives_nothing_real_to_point_at(self):
        self.assertEqual(self.check(["rateLimit"], title="No rate limit")["status"], UNVERIFIED)

    def test_docs_tests_and_manifests_neither_enforce_nor_switch_off_anything(self):
        r = self.check(["helmet"], title="No security headers")      # only in README, a test file and package.json
        self.assertEqual(r["status"], UNVERIFIED)

    def test_names_match_whole_words_only(self):
        r = self.check(["secure"], title="Cookie is not marked secure")   # `insecureMode` is live code but a different word
        self.assertEqual((r["status"], r["code"]), (CONFIRMED, "confirmed_absent"))
        self.assertEqual(r["evidence"][0]["line"], line_of(SERVER, "secure: true"))

    def test_a_line_that_matches_two_names_is_listed_once(self):
        r = self.check(["csrf", "csurf"], title="No CSRF protection")       # `// const csrf = require("csurf");` has both
        lines = [e["line"] for e in r["evidence"]]
        self.assertEqual(r["status"], CONFIRMED)
        self.assertEqual(len(lines), len(set(lines)))
        self.assertEqual(lines[0], line_of(SERVER, 'const csrf = require("csurf")'))

    def test_unusable_names_are_ignored(self):
        for names in ([], ["ab"], ["http only"], [5, None], "httpOnly", None):
            with self.subTest(names=names):
                self.assertEqual(self.check(names)["status"], UNVERIFIED)

    def test_the_defender_can_still_overturn_it_by_quoting_live_code(self):
        r = self.check(["httpOnly"], defend={"defence_found": True, "reasoning": "set elsewhere",
                                              "evidence": [ev("server.js", "secret: cookieSecret,")]})
        self.assertEqual((r["status"], r["code"]), (REFUTED, "defence_found"))

    def test_the_claimed_harm_must_still_follow(self):
        r = self.check(["httpOnly"], impact=False)
        self.assertEqual((r["status"], r["code"]), (REFUTED, "impact_does_not_follow"))

    def test_the_names_are_given_to_the_defender_as_places_to_look(self):
        idx = CodeIndex.from_dir(make_repo(REPO))
        llm = ScriptedLLM(verify_locate=locate(["server.js"], ["httpOnly"]), verify_judge=absent_reply(["httpOnly"]),
                          verify_defend={"defence_found": False, "reasoning": "none", "evidence": []})
        CodeVerifier(idx, llm).check(finding("Session cookies lack httpOnly"))
        self.assertEqual(len(llm.prompts("verify_defend")), 1)
        self.assertIn("REPO-WIDE LITERAL SEARCH", llm.prompts("verify_defend")[0])
        self.assertIn("'httpOnly'", llm.prompts("verify_defend")[0])


if __name__ == "__main__":
    unittest.main()
