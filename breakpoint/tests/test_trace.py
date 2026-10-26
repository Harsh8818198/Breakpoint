import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from breakpoint.codeindex import CodeIndex
from breakpoint.codeverify import CodeVerifier
from breakpoint.evaluation.runner import run_eval
from breakpoint.evaluation.sets import load_set
from breakpoint.proof import ProvenVerifier
from breakpoint.trace import load_entries, main as trace_main, pick, render

from .test_codeindex import make_repo
from .test_codeverify import AUTH, DB, SQL_LINE, STATE_CHECK, UPHELD, ScriptedLLM, ev, finding, locate
from .test_evaluation import EVAL_LINE as HANDLER_EVAL, Fake, plain_reply, write_set
from .test_exploit import EVAL_LINE, LIB, README, reply
from .test_exploit import finding as eval_finding
from .test_proof import CONFIRM, NO_DEFENCE, UNPROVEN, model, seq

SQL_CONFIRM = {"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "string concatenation", "evidence": [ev("db.py", SQL_LINE, 2)]}


def steps(r):
    return [s["step"] for s in r["trace"]]


class StepsOfOneCheck(unittest.TestCase):
    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo({"auth.py": AUTH, "db.py": DB}))

    def check(self, llm, f=None, **kw):
        return CodeVerifier(self.idx, llm, **kw).check(f or finding("SQL injection in get_user"))

    def test_a_confirmed_claim_shows_every_step_in_order_with_what_each_saw(self):
        r = self.check(ScriptedLLM(verify_locate=locate(["db.py"], ["execute"]), verify_judge=SQL_CONFIRM, verify_defend=NO_DEFENCE))
        self.assertEqual(steps(r), ["locate", "read", "judge", "mechanical", "defend", "decision"])
        t = {s["step"]: s for s in r["trace"]}
        self.assertEqual(t["locate"]["files"], ["db.py"])
        self.assertIn("db.py", t["read"]["files"])
        self.assertEqual((t["judge"]["verdict"], t["judge"]["impact_follows"]), ("CONFIRMED", True))
        self.assertEqual(t["judge"]["quotes"][0]["quote"], SQL_LINE)
        self.assertEqual((t["mechanical"]["quotes"][0]["line"], t["mechanical"]["quotes"][0]["result"]), (2, "found, live code"))
        self.assertEqual((t["defend"]["defence_found"], t["defend"]["outcome"]), (False, "no protection found: the claim stands"))
        self.assertEqual((t["decision"]["status"], t["decision"]["code"]), ("CONFIRMED", "confirmed"))

    def test_an_invented_quote_is_visible_as_not_found_and_nothing_after_it_runs(self):
        bad = {"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "r", "evidence": [ev("db.py", "db.execute(raw_sql_from_user)")]}
        r = self.check(ScriptedLLM(verify_locate=locate(["db.py"], ["execute"]), verify_judge=bad))
        self.assertEqual(steps(r), ["locate", "read", "judge", "mechanical", "decision"])
        q = r["trace"][3]["quotes"][0]
        self.assertEqual((q["line"], q["result"]), (None, "quote not found in the file"))
        self.assertEqual(r["trace"][-1]["code"], "quote_not_in_code")

    def test_a_quote_that_is_a_comment_is_visible_as_a_comment(self):
        idx = CodeIndex.from_dir(make_repo({"app.py": "# if not csrf_ok(request): abort(403)\nhandle(request)\n"}))
        judge = {"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "r", "evidence": [ev("app.py", "if not csrf_ok(request): abort(403)", 1)]}
        r = CodeVerifier(idx, ScriptedLLM(verify_locate=locate(["app.py"], ["csrf"]), verify_judge=judge)).check(finding("No CSRF check"))
        self.assertEqual(r["trace"][3]["quotes"][0]["result"], "found, but it is a comment, not live code")
        self.assertEqual(r["trace"][-1]["code"], "quote_is_comment")

    def test_a_refutation_that_stands_shows_the_appeal_and_why(self):
        refute = {"verdict": "REFUTED", "reasoning": "state is compared to the session value", "evidence": [ev("auth.py", STATE_CHECK, 3)]}
        r = self.check(ScriptedLLM(verify_locate=locate(), verify_judge=refute, verify_appeal=UPHELD), finding("Missing state check on OAuth callback"))
        self.assertEqual(steps(r), ["locate", "read", "judge", "mechanical", "appeal", "decision"])
        a = r["trace"][4]
        self.assertEqual(a["outcome"], "the refutation holds")
        self.assertIn("auth.py:3", a["refutation_cited"][0])

    def test_an_appeal_that_overturns_a_refutation_is_shown_with_the_live_code_it_quoted(self):
        refute = {"verdict": "REFUTED", "reasoning": "r", "evidence": [ev("auth.py", STATE_CHECK, 3)]}
        appeal = {"refutation_holds": False, "impact_follows": True, "reasoning": "the check is never applied", "evidence": [ev("db.py", SQL_LINE, 2)]}
        r = self.check(ScriptedLLM(verify_locate=locate(["db.py", "auth.py"], ["state"]), verify_judge=refute, verify_appeal=appeal,
                                   verify_defend=NO_DEFENCE), finding("Missing state check on OAuth callback"))
        self.assertEqual(steps(r), ["locate", "read", "judge", "mechanical", "appeal", "defend", "decision"])
        a = r["trace"][4]
        self.assertTrue(a["outcome"].startswith("overturned"))
        self.assertEqual(a["quotes"][0]["result"], "found, live code")
        self.assertEqual(r["trace"][-1]["code"], "confirmed_on_appeal")

    def test_a_defender_that_quotes_real_code_is_shown_defeating_the_claim(self):
        defend = {"defence_found": True, "reasoning": "state is checked", "evidence": [ev("auth.py", STATE_CHECK)]}
        r = self.check(ScriptedLLM(verify_locate=locate(["db.py", "auth.py"], ["execute"]), verify_judge=SQL_CONFIRM, verify_defend=defend))
        d = r["trace"][-2]
        self.assertEqual(d["step"], "defend")
        self.assertTrue(d["outcome"].startswith("defeated"))
        self.assertEqual(d["quotes"][0]["result"], "found, live code")
        self.assertEqual(r["trace"][-1]["code"], "defence_found")

    def test_a_defender_that_quotes_nothing_real_is_shown_not_counting(self):
        defend = {"defence_found": True, "reasoning": "trust me", "evidence": [ev("auth.py", "invented protective code here")]}
        r = self.check(ScriptedLLM(verify_locate=locate(["db.py"], ["execute"]), verify_judge=SQL_CONFIRM, verify_defend=defend))
        d = r["trace"][-2]
        self.assertIn("quoted no real live code", d["outcome"])
        self.assertEqual(d["quotes"][0]["result"], "quote not found in the file")
        self.assertEqual(r["status"], "CONFIRMED")

    def test_a_second_look_is_shown_with_what_the_reviewer_asked_for(self):
        first = {"verdict": "UNVERIFIABLE", "reasoning": "need the body of get_user", "need_to_see": ["get_user"], "evidence": []}
        r = self.check(ScriptedLLM(verify_locate=locate(["auth.py"], ["state"]), verify_judge=seq(first, SQL_CONFIRM), verify_defend=NO_DEFENCE))
        self.assertEqual(steps(r)[:5], ["locate", "read", "judge", "look_again", "judge (second look)"])
        self.assertEqual(r["trace"][3]["asked_for"], ["get_user"])
        self.assertEqual(r["trace"][4]["verdict"], "CONFIRMED")

    def test_a_missing_protection_shows_the_search_that_proved_it(self):
        idx = CodeIndex.from_dir(make_repo({"app.js": "// app.use(helmet())\napp.listen(3000)\n"}))
        judge = {"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "no security headers", "evidence": [], "absent_names": ["helmet"]}
        r = CodeVerifier(idx, ScriptedLLM(verify_locate=locate(["app.js"], ["helmet"]), verify_judge=judge, verify_defend=NO_DEFENCE)).check(
            finding("No security headers"))
        a = next(s for s in r["trace"] if s["step"] == "absence_search")
        self.assertEqual((a["names"], a["proved"], a["switched_off_at"]), (["helmet"], True, ["app.js:1"]))

    def test_a_failed_check_keeps_the_steps_taken_before_it_failed(self):
        r = self.check(ScriptedLLM(verify_locate=locate(["db.py"], ["execute"]), verify_judge=RuntimeError("HTTP 500")))
        self.assertEqual(steps(r), ["locate", "read", "error", "decision"])
        self.assertIn("HTTP 500", r["trace"][2]["message"])

    def test_the_trace_stays_out_of_the_results_unless_asked_for(self):
        llm = ScriptedLLM(verify_locate=locate(["db.py"], ["execute"]), verify_judge=SQL_CONFIRM, verify_defend=NO_DEFENCE)
        plain = CodeVerifier(self.idx, llm)
        out = plain([finding("SQL injection in get_user")])
        self.assertNotIn("trace", out[0])
        self.assertNotIn("trace", plain.records[0])
        traced = CodeVerifier(self.idx, llm, trace=True)
        out = traced([finding("SQL injection in get_user")])
        self.assertEqual(out[0]["trace"][0]["step"], "locate")
        self.assertIn("trace", traced.records[0])


class VotesAndExploitability(unittest.TestCase):
    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo({"lib.js": LIB, "README.md": README}))

    def test_each_check_and_each_exploitability_answer_is_kept_with_the_votes(self):
        v = ProvenVerifier(self.idx, model(seq(CONFIRM, UNPROVEN, CONFIRM)), trace=True)
        r = v([eval_finding()])[0]
        t = r["trace"]
        self.assertEqual([c["status"] for c in t["code_checks"]], ["CONFIRMED", "UNVERIFIED", "CONFIRMED"])
        self.assertEqual(len(t["exploit"]), 2)
        self.assertEqual(t["votes"]["code_check"]["confirmed"], 2)
        self.assertEqual(t["verdict"], {"status": "CONFIRMED", "code": "confirmed"})
        self.assertEqual(t["exploit"][0]["entry_checked"]["result"], "found, live code")
        self.assertEqual(v.records[0]["trace"], t)

    def test_without_trace_the_strict_verifier_adds_nothing_to_results_or_records(self):
        v = ProvenVerifier(self.idx, model(CONFIRM))
        r = v([eval_finding()])[0]
        self.assertNotIn("trace", r)
        self.assertNotIn("trace", v.records[0])


class ThePage(unittest.TestCase):
    def entry(self, llm, trace=True, **kw):
        idx = CodeIndex.from_dir(make_repo({"lib.js": LIB, "README.md": README}))
        v = ProvenVerifier(idx, llm, trace=trace, **kw)
        r = v([eval_finding("Code execution through eval of the document")])[0]
        return {"title": "Code execution through eval of the document", "claim": "the document text reaches eval", "outcome":
                "kept" if r["status"] == "CONFIRMED" else f"{r['status']}:{r['code']}", "votes": r["votes"], "exploit": r["exploit"],
                "trace": r["trace"]}

    def test_a_finding_prints_every_step_the_checks_and_the_rules_it_passed(self):
        page = render(self.entry(model(CONFIRM)))
        for text in ("CLAIM", "RESULT", "FINDING (exploitable)", "2 of 2 code checks held", "CODE CHECK 1 of 2: held", "locate", "read", "judge",
                     "mechanical", "found, live code", "defender", "protection found: no", "decision", "EXPLOITABILITY 1 of 2", "entry point",
                     "attacker", "untrusted_content", "path", "rules", "attacker is outside the trust boundary [ok]",
                     "entry point is live code [ok]", "no power already held [ok]"):
            self.assertIn(text, page)
        self.assertLess(len(page.splitlines()), 90)

    def test_later_checks_are_one_line_each_unless_everything_is_asked_for(self):
        e = self.entry(model(CONFIRM))
        short, full = render(e), render(e, all_votes=True)
        self.assertIn("CODE CHECK 2 of 2: held (confirmed)", short)
        self.assertNotIn("CODE CHECK 2 of 2: held (", full)
        self.assertGreater(len(full.splitlines()), len(short.splitlines()))
        self.assertIn("EXPLOITABILITY 2 of 2", full)

    def test_an_accurate_claim_the_operator_controls_prints_as_not_a_finding_with_the_failed_rule(self):
        page = render(self.entry(model(CONFIRM, exploit=reply(attacker="operator", tier="not_exploitable"))))
        self.assertIn("NOT A FINDING: accurate about the code but not exploitable", page)
        self.assertIn("attacker is outside the trust boundary [FAILED]", page)

    def test_a_refuted_claim_prints_why_it_was_not_kept(self):
        refute = {"verdict": "REFUTED", "reasoning": "x", "evidence": [ev("lib.js", "class Loader {", 5)]}
        llm = ScriptedLLM(verify_locate=locate(["lib.js"], ["eval"]), verify_judge=refute, verify_appeal=UPHELD, verify_defend=NO_DEFENCE, exploit=reply())
        page = render(self.entry(llm))
        self.assertIn("NOT KEPT (refuted: contradicted_by_code)", page)
        self.assertIn("appeal", page)
        self.assertNotIn("EXPLOITABILITY", page)

    def test_the_steps_of_one_plain_check_print_too(self):
        idx = CodeIndex.from_dir(make_repo({"lib.js": LIB}))
        r = CodeVerifier(idx, ScriptedLLM(verify_locate=locate(["lib.js"], ["eval"]), verify_judge=CONFIRM, verify_defend=NO_DEFENCE)).check(eval_finding())
        page = render({"title": "t", "claim": "c", "outcome": "kept", "trace": r["trace"]})
        self.assertIn("CODE CHECK 1 of 1", page)
        self.assertIn("mechanical", page)


class SavedRunsAndTheCommand(unittest.TestCase):
    def run_one(self, **opts):
        es = load_set(str(write_set()))
        out, cache = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        llm = Fake(baseline=plain_reply(), verify_locate=locate(["routes/handler.js"], ["eval"]), verify_defend=NO_DEFENCE,
                   verify_judge={"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "eval of the body",
                                 "evidence": [ev("routes/handler.js", HANDLER_EVAL, 12)]})
        files = run_eval(es, "raw", ["plain"], 1, out, cache, llm=llm, opts=opts, log=lambda *_: None)
        return files[0]

    def test_a_run_saved_with_trace_keeps_each_claims_steps_and_text(self):
        rec = json.loads(self.run_one(checks=1, trace=True).read_text(encoding="utf-8"))
        p = rec["proposed"][0]
        self.assertEqual(p["outcome"], "kept")
        self.assertEqual(p["trace"]["code_checks"][0]["steps"][0]["step"], "locate")
        self.assertEqual(p["votes"]["code_check"]["cast"], 1)
        self.assertEqual(p["evidence"][0]["line"], 12)
        self.assertIn("eval of the body", p["claim"])
        self.assertTrue(rec["verify_config"]["trace"])

    def test_a_run_saved_without_trace_stays_small(self):
        rec = json.loads(self.run_one(checks=1).read_text(encoding="utf-8"))
        self.assertNotIn("trace", rec["proposed"][0])
        self.assertNotIn("trace", rec["verify_config"])

    def test_show_lists_the_claims_and_prints_one_page(self):
        f = self.run_one(checks=1, trace=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(trace_main(["show", str(f)]), 0)
        listing = buf.getvalue()
        self.assertIn("trace", listing)
        self.assertIn("kept", listing)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            trace_main(["show", str(f), "--index", "0"])
        self.assertIn("CODE CHECK 1 of 1", buf.getvalue())
        self.assertIn("routes/handler.js", buf.getvalue())

    def test_a_claim_without_a_trace_says_how_to_get_one(self):
        f = self.run_one(checks=1)
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
            trace_main(["show", str(f), "--index", "0"])
        self.assertIn("--trace", str(cm.exception))

    def test_choosing_a_claim_by_index_or_title_and_refusing_an_ambiguous_choice(self):
        entries = [{"title": "SQL injection in search"}, {"title": "SQL injection in login"}, {"title": "Open redirect"}]
        self.assertEqual(pick(entries, 2, None)["title"], "Open redirect")
        self.assertEqual(pick(entries, None, "redirect")["title"], "Open redirect")
        with self.assertRaises(ValueError):
            pick(entries, None, "sql")
        with self.assertRaises(ValueError):
            pick(entries, 9, None)
        with self.assertRaises(ValueError):
            pick(entries, None, None)

    def test_a_saved_single_trace_loads(self):
        p = Path(tempfile.mkdtemp()) / "t.json"
        p.write_text(json.dumps({"title": "x", "claim": "c", "outcome": "kept", "trace": {"code_checks": [], "exploit": []}}), encoding="utf-8")
        self.assertEqual(len(load_entries(str(p))), 1)


if __name__ == "__main__":
    unittest.main()
