import json
import os
import tempfile
import unittest

from breakpoint.codeindex import CodeIndex
from breakpoint.llm import LLMFatalError
from breakpoint.routemap import map_routes
from breakpoint.routereview import (Task, applies, build_prompt, merge_duplicates, plan, review, run_route_review,
                                    to_finding)

from tests.test_codeindex import make_repo
from tests.test_codeverify import ScriptedLLM
from tests.test_routemap import APP

EVAL_LINE = "const n = eval(req.body.n);"


class Fake(ScriptedLLM):
    provider, model = "fake", "fake-1"


def build(files=None):
    idx = CodeIndex.from_dir(make_repo(files or APP))
    return idx, map_routes(idx)


def findings_reply(*items):
    return {"findings": list(items)}


def eval_finding(**kw):
    d = {"title": "eval on request body", "attack_category": "injection", "description": "eval of req.body.n",
         "steps_to_exploit": ["post a payload"], "impact": "remote code execution", "exploitability": 9, "impact_score": 9,
         "spread": 5, "fix_difficulty": 1,
         "code_refs": [{"file": "routes/handler.js", "line": 12, "quote": EVAL_LINE},
                       {"file": "routes/handler.js", "line": 1, "quote": "a line that is not in the file at all"}]}
    d.update(kw)
    return d


class WhichQuestionsAreAsked(unittest.TestCase):
    def test_a_route_is_only_asked_what_its_own_facts_allow(self):
        _, rm = build()
        by = {}
        for t in plan(rm):
            by.setdefault(t.focus, []).append(t.label)
        self.assertEqual(sorted(by["authz"]), ["GET /a", "GET /api/ping", "GET /go", "POST /a"])      # always
        self.assertEqual(sorted(by["injection"]), ["GET /a", "POST /a"])      # reads input AND reaches eval / a query
        self.assertEqual(by["outbound"], ["GET /go"])                          # only the redirect
        self.assertNotIn("session", by)                                        # nothing here touches sessions or passwords
        self.assertEqual(by["app"], ["app-wide setup"])                        # once

    def test_login_like_paths_get_the_session_question(self):
        files = dict(APP)
        files["routes/index.js"] = files["routes/index.js"].replace('app.get("port");', 'app.post("/login", (req, res) => res.send("x"));')
        _, rm = build(files)
        self.assertIn("POST /login", [t.label for t in plan(rm) if t.focus == "session"])

    def test_the_app_wide_review_comes_first_so_a_call_cap_never_drops_it(self):
        _, rm = build()
        self.assertEqual(plan(rm)[0], Task("app"))


class WhatTheReviewerIsShown(unittest.TestCase):
    def setUp(self):
        self.idx, self.rm = build()

    def prompt(self, focus, label):
        route = next(r for r in self.rm.routes if r.label == label)
        return build_prompt(Task(focus, route), self.rm, self.idx, max_chars=14000, max_findings=3)

    def test_a_route_prompt_carries_its_code_its_protections_and_its_switched_off_variant(self):
        text = self.prompt("authz", "POST /a")
        for needle in ("FOCUS: Access control", "protections in front of it: isLoggedIn", "passport.authenticate",
                       "SWITCHED OFF", "isAdmin", EVAL_LINE, "req.session.id", "NOT active code"):
            self.assertIn(needle, text)
        self.assertNotIn("this.fetch", text)                  # the other route's database code is not in this prompt
        self.assertNotIn("a line that is not in the file", text)

    def test_the_app_prompt_lists_what_is_active_and_what_is_switched_off(self):
        text = build_prompt(Task("app"), self.rm, self.idx, max_chars=14000, max_findings=3)
        self.assertIn("THE APP SETUP", text)
        self.assertIn("switched off (commented out, does NOT run): server.js:6 csrf()", text)
        self.assertIn("bodyParser.json()", text)
        self.assertIn('app.use("/api", apiRouter);', text)    # the entry file itself is in front of the reviewer


class WhatComesBack(unittest.TestCase):
    def setUp(self):
        self.idx, self.rm = build()

    def run_review(self, reply, **kw):
        llm = Fake(route_review=reply)
        return llm, review(self.idx, llm, self.rm, log=lambda *_: None, **kw)

    def test_findings_keep_only_citations_that_exist_and_are_attributed_to_the_reviewer(self):
        def reply(user):
            return findings_reply(eval_finding()) if "FOCUS: Untrusted input" in user and "POST /a" in user else findings_reply()
        llm, res = self.run_review(reply)
        self.assertEqual(len(res.findings), 1)
        f = res.findings[0]
        self.assertEqual(f.code_refs, [{"file": "routes/handler.js", "line": 12, "quote": EVAL_LINE}])   # the invented quote is gone
        self.assertEqual(f.discovered_by, "Untrusted input reaching an interpreter reviewer: POST /a")
        self.assertEqual((f.attack_category, f.exploitability, f.fix_difficulty), ("injection", 9, 1))
        self.assertEqual(len(llm.prompts("route_review")), 8)

    def test_bad_values_fall_back_instead_of_crashing(self):
        d = eval_finding(attack_category="made-up", exploitability="lots", fix_difficulty=99, steps_to_exploit="just do it")
        f = to_finding(d, Task("outbound", self.rm.routes[0]), self.idx)
        self.assertEqual((f.attack_category, f.exploitability, f.fix_difficulty), ("injection", 0, 10))
        self.assertEqual(f.steps_to_exploit, ["just do it"])

    def test_the_same_bug_seen_on_two_routes_is_reported_once_with_both_places(self):
        def reply(user):
            if "FOCUS: Access control" in user and ("GET /a " in user or "POST /a " in user):
                return findings_reply({"title": "Missing admin check on /a", "attack_category": "authz", "description": "d",
                                       "code_refs": [{"file": "routes/index.js", "line": 6, "quote": 'app.get("/a", isLoggedIn, cors, h.show);'}]})
            return findings_reply()
        _, res = self.run_review(reply)
        self.assertEqual(res.candidates, 2)
        self.assertEqual(len(res.findings), 1)
        self.assertIn("GET /a", res.findings[0].discovered_by)
        self.assertIn("POST /a", res.findings[0].discovered_by)

    def test_different_bugs_in_different_places_are_not_merged(self):
        a = to_finding({"title": "Open redirect on go", "attack_category": "injection", "description": "d"}, Task("outbound", self.rm.routes[0]), self.idx)
        b = to_finding({"title": "Eval on the save handler", "attack_category": "injection", "description": "d"}, Task("injection", self.rm.routes[0]), self.idx)
        self.assertEqual(len(merge_duplicates([a, b])), 2)

    def test_one_garbled_reply_does_not_lose_the_other_reviews(self):
        calls = {"n": 0}

        def reply(user):
            calls["n"] += 1
            if calls["n"] == 3:
                return "I am sorry, I cannot do JSON today"
            return findings_reply(eval_finding()) if "FOCUS: Untrusted input" in user and "POST /a" in user else findings_reply()
        _, res = self.run_review(reply)
        self.assertEqual(len(res.errors), 1)
        self.assertEqual(len(res.findings), 1)

    def test_a_fatal_provider_error_stops_the_run(self):
        with self.assertRaises(LLMFatalError):
            self.run_review(LLMFatalError("no credit left"))

    def test_the_call_cap_limits_spend_and_says_what_it_skipped(self):
        llm, res = self.run_review(findings_reply(), max_calls=3)
        self.assertEqual(len(llm.prompts("route_review")), 3)
        self.assertEqual(res.skipped_by_cap, 5)


class EndToEnd(unittest.TestCase):
    class ConfirmAll:
        def __init__(self, index, llm):
            self.n = 0

        def __call__(self, findings):
            self.n = len(findings)
            return [{"status": "CONFIRMED", "evidence_items": f.code_refs} for f in findings]

        def stats(self):
            return {"checked": self.n, "confirmed": self.n, "refuted": 0, "unverified": 0, "errors": 0}

    def run(self, verify=True, files=None):
        root = make_repo(files or APP)
        out = os.path.join(tempfile.mkdtemp(prefix="bp_review_"), "out.json")

        def reply(user):
            return findings_reply(eval_finding()) if "FOCUS: Untrusted input" in user and "POST /a" in user else findings_reply()
        llm = Fake(route_review=reply)
        data = run_route_review(root, out, verify=verify, llm=llm, verifier_factory=self.ConfirmAll)
        with open(out, encoding="utf-8") as fh:
            return data, json.load(fh)

    def test_the_saved_report_has_the_shape_the_scorer_and_verify_report_read(self):
        data, saved = self.run()
        self.assertEqual(saved["route_review"]["reviews"], 8)
        self.assertTrue(saved["route_review"]["checked_against_code"])
        f = saved["findings"][0]
        self.assertEqual(f["verification"], "CONFIRMED")
        self.assertEqual(f["evidence"], [{"file": "routes/handler.js", "line": 12, "quote": EVAL_LINE}])
        from breakpoint.run import _finding_from_dict
        self.assertEqual(_finding_from_dict(f).title, "eval on request body")

    def test_without_the_code_check_the_report_says_so(self):
        _, saved = self.run(verify=False)
        self.assertFalse(saved["route_review"]["checked_against_code"])
        self.assertEqual(saved["findings"][0]["verification"], "")
        self.assertIsNone(saved["verification"])

    def test_a_provider_failure_while_checking_does_not_lose_the_reviews(self):
        class Dies:
            def __init__(self, index, llm): pass
            def __call__(self, findings): raise LLMFatalError("key rejected")

        root = make_repo(APP)
        out = os.path.join(tempfile.mkdtemp(prefix="bp_review_"), "out.json")

        def reply(user):
            return findings_reply(eval_finding()) if "FOCUS: Untrusted input" in user and "POST /a" in user else findings_reply()
        with self.assertRaises(LLMFatalError):
            run_route_review(root, out, llm=Fake(route_review=reply), verifier_factory=Dies)
        with open(out, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(len(saved["findings"]), 1)
        self.assertFalse(saved["route_review"]["checked_against_code"])
        self.assertIn("not yet checked", saved["route_review"]["stage"])

    def test_a_repo_with_no_express_app_stops_with_a_clear_message(self):
        with self.assertRaises(SystemExit) as cm:
            self.run(files={"app.py": "print('hi')\n"})
        self.assertIn("Express", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
