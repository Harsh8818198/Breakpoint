import unittest

from breakpoint.codeindex import CodeIndex
from breakpoint.codeverify import CONFIRMED, ERROR, UNVERIFIED, CodeVerifier, apply_result
from breakpoint.llm import LLMFatalError
from breakpoint.models import Blueprint, Finding
from breakpoint.proof import OBSERVATION, ProvenVerifier, make_verifier, vote
from breakpoint.report import render_report

from .test_codeindex import make_repo
from .test_codeverify import ScriptedLLM, ev, locate
from .test_exploit import EVAL_LINE, LIB, README, finding, reply

CONFIRM = {"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "eval of the argument", "evidence": [ev("lib.js", EVAL_LINE, 2)]}
UNPROVEN = {"verdict": "UNVERIFIABLE", "evidence": []}
NO_DEFENCE = {"defence_found": False, "reasoning": "nothing blocks it", "evidence": []}


def seq(*replies):
    """A model that answers differently on each call, in order."""
    it = iter(replies)
    return lambda user: next(it)


def model(judge, exploit=None):
    return ScriptedLLM(verify_locate=locate(["lib.js"], ["eval"]), verify_judge=judge, verify_defend=NO_DEFENCE,
                       exploit=exploit if exploit is not None else reply())


class Voting(unittest.TestCase):
    def run_vote(self, answers, checks):
        it = iter(answers)
        return vote(lambda: next(it), lambda a: a is True, lambda a: a == "err", checks)

    def test_it_stops_as_soon_as_a_majority_agrees(self):
        answers, yes, no, errors = self.run_vote([True, True, False], 3)
        self.assertEqual((answers, yes, no, errors), ([True, True], 2, 0, 0))
        self.assertEqual(self.run_vote([False, False, True], 3)[1:3], (0, 2))

    def test_a_split_goes_to_the_third_vote(self):
        answers, yes, no, _ = self.run_vote([True, False, True], 3)
        self.assertEqual((len(answers), yes, no), (3, 2, 1))

    def test_one_check_is_one_call(self):
        answers, yes, no, _ = self.run_vote([False, True], 1)
        self.assertEqual((len(answers), yes, no), (1, 0, 1))

    def test_an_error_is_not_a_vote_but_is_tried_again(self):
        answers, yes, no, errors = self.run_vote(["err", True, "err", True], 3)
        self.assertEqual((yes, no, errors), (2, 0, 2))

    def test_a_check_that_keeps_failing_gives_up(self):
        answers, yes, no, errors = self.run_vote(["err"] * 10, 3)
        self.assertEqual((answers, yes, no, errors), ([], 0, 0, 3))

    def test_with_an_even_number_of_checks_a_tie_is_left_to_the_caller(self):
        answers, yes, no, _ = self.run_vote([True, False], 2)
        self.assertEqual((yes, no), (1, 1))


class Checking(unittest.TestCase):
    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo({"lib.js": LIB, "README.md": README}))

    def verify(self, llm, f=None, **kw):
        v = ProvenVerifier(self.idx, llm, **kw)
        return v.check(f or finding()), v

    def test_two_agreeing_checks_settle_it_and_the_result_says_how_many_agreed(self):
        llm = model(CONFIRM)
        r, _ = self.verify(llm)
        self.assertEqual(r["status"], CONFIRMED)
        self.assertEqual(r["votes"]["code_check"], {"confirmed": 2, "cast": 2, "errors": 0})
        self.assertEqual(len(llm.prompts("verify_judge")), 2)                 # not three: the second agreed with the first
        self.assertEqual(r["exploit"]["tier"], "exploitable")
        self.assertEqual(r["exploit"]["agreement"], "2/2")

    def test_a_claim_that_flips_gets_a_third_check_and_the_majority_wins(self):
        llm = model(seq(CONFIRM, UNPROVEN, CONFIRM))
        r, _ = self.verify(llm)
        self.assertEqual((r["status"], r["votes"]["code_check"]["confirmed"], r["votes"]["code_check"]["cast"]), (CONFIRMED, 2, 3))
        self.assertEqual(len(llm.prompts("verify_judge")), 3)

    def test_a_true_flaw_refuted_by_one_unlucky_check_is_recovered(self):
        llm = model(seq(UNPROVEN, CONFIRM, CONFIRM))
        r, _ = self.verify(llm)
        self.assertEqual(r["status"], CONFIRMED)

    def test_a_claim_rejected_twice_is_not_checked_a_third_time(self):
        llm = model(seq(UNPROVEN, UNPROVEN, CONFIRM))
        r, _ = self.verify(llm)
        self.assertEqual(r["status"], UNVERIFIED)
        self.assertEqual(len(llm.prompts("verify_judge")), 2)
        self.assertEqual(llm.prompts("exploit"), [])                          # an unconfirmed claim is never judged for exploitability

    def test_a_tie_with_two_checks_is_not_a_confirmation(self):
        llm = model(seq(CONFIRM, UNPROVEN))
        r, _ = self.verify(llm, checks=2)
        self.assertEqual(r["status"], UNVERIFIED)

    def test_one_check_without_exploitability_is_the_old_single_check(self):
        llm = model(CONFIRM)
        r, _ = self.verify(llm, checks=1, exploit=False)
        self.assertEqual(r["status"], CONFIRMED)
        self.assertEqual(len(llm.prompts("verify_judge")), 1)
        self.assertEqual(llm.prompts("exploit"), [])
        self.assertNotIn("exploit", r)
        plain = CodeVerifier(self.idx, model(CONFIRM)).check(finding())
        self.assertEqual((r["status"], r["code"], r["evidence"]), (plain["status"], plain["code"], plain["evidence"]))

    def test_every_check_failing_is_an_error_not_a_rejection(self):
        r, _ = self.verify(model(RuntimeError("HTTP 500")))
        self.assertEqual(r["status"], ERROR)

    def test_a_fatal_provider_error_stops_the_run(self):
        with self.assertRaises(LLMFatalError):
            self.verify(model(LLMFatalError("no credit")))
        with self.assertRaises(LLMFatalError):
            self.verify(model(CONFIRM, exploit=LLMFatalError("no credit")))

    def test_checks_below_one_is_refused(self):
        with self.assertRaises(ValueError):
            ProvenVerifier(self.idx, model(CONFIRM), checks=0)


class Exploitability(unittest.TestCase):
    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo({"lib.js": LIB, "README.md": README}))

    def verify(self, llm, **kw):
        v = ProvenVerifier(self.idx, llm, **kw)
        out = v([finding()])
        return out[0], v

    def test_an_accurate_claim_the_operator_controls_is_an_observation_not_a_finding(self):
        llm = model(CONFIRM, exploit=reply(attacker="operator", tier="not_exploitable"))
        r, v = self.verify(llm)
        self.assertEqual((r["ok"], r["status"], r["code"]), (False, OBSERVATION, "attacker_is_trusted"))
        self.assertEqual(r["evidence_items"][0]["line"], 2)                    # the accurate evidence is still there
        self.assertTrue(r["evidence"].startswith("ACCURATE BUT NOT EXPLOITABLE"))
        s = v.stats()
        self.assertEqual((s["confirmed"], s["observations"], s["checked"]), (0, 1, 1))
        self.assertEqual(s["rejected"][0]["status"], OBSERVATION)
        self.assertIn("operator", s["rejected"][0]["why"])

    def test_an_exploitable_claim_stays_a_finding_and_carries_the_entry_point_and_path(self):
        r, v = self.verify(model(CONFIRM))
        self.assertTrue(r["ok"])
        x = r["exploit"]
        self.assertEqual((x["tier"], x["attacker"], x["entry_point"]["line"]), ("exploitable", "untrusted_content", 2))
        self.assertIn("eval", x["path"])
        self.assertEqual(v.stats()["confirmed"], 1)

    def test_the_exploitability_vote_is_a_majority_and_a_split_is_visible(self):
        no = reply(attacker="operator", tier="not_exploitable")
        r, v = self.verify(model(CONFIRM, exploit=seq(no, reply(), reply())))
        self.assertEqual((r["status"], r["votes"]["exploit"]["yes"], r["votes"]["exploit"]["cast"]), (CONFIRMED, 2, 3))
        self.assertEqual(r["exploit"]["agreement"], "2/3")
        self.assertEqual(v.stats()["split_decisions"], 1)

    def test_a_majority_against_makes_it_an_observation_with_the_common_reason(self):
        no = reply(attacker="operator", tier="not_exploitable")
        r, _ = self.verify(model(CONFIRM, exploit=seq(reply(), no, no)))
        self.assertEqual((r["status"], r["code"]), (OBSERVATION, "attacker_is_trusted"))

    def test_when_votes_differ_between_exploitable_and_conditional_the_cautious_label_wins(self):
        cond = reply(tier="conditional", condition="only if the app passes request bodies")
        r, _ = self.verify(model(CONFIRM, exploit=seq(reply(), cond)))
        self.assertEqual(r["exploit"]["tier"], "conditional")
        self.assertEqual(r["exploit"]["condition"], "only if the app passes request bodies")

    def test_if_the_exploitability_check_never_runs_the_claim_stays_confirmed_and_says_it_is_unchecked(self):
        r, _ = self.verify(model(CONFIRM, exploit=RuntimeError("HTTP 500")))
        self.assertEqual((r["status"], r["exploit"]["tier"]), (CONFIRMED, "unchecked"))

    def test_the_confirmed_result_is_recorded_on_the_finding_and_survives_a_round_trip(self):
        r, _ = self.verify(model(CONFIRM))
        f = finding()
        apply_result(f, r)
        d = f.to_dict()
        self.assertEqual((f.verification, d["exploit"]["tier"], d["votes"]["code_check"]["cast"]), ("CONFIRMED", "exploitable", 2))
        from breakpoint.run import _finding_from_dict
        self.assertEqual(_finding_from_dict(d).exploit["tier"], "exploitable")

    def test_make_verifier_builds_the_stricter_one(self):
        v = make_verifier(self.idx, model(CONFIRM), checks=2, exploit=False)
        self.assertIsInstance(v, ProvenVerifier)
        self.assertEqual((v.checks, v.exploit), (2, False))


class Reporting(unittest.TestCase):
    def test_the_report_says_how_exploitable_a_finding_is_and_how_many_checks_agreed(self):
        f = finding()
        f.evidence = [{"file": "lib.js", "line": 2, "quote": EVAL_LINE}]
        f.exploit = {"tier": "conditional", "agreement": "2/3", "attacker": "untrusted_content", "path": "text reaches eval",
                     "condition": "the app passes request bodies", "entry_point": {"file": "lib.js", "line": 2, "quote": EVAL_LINE}}
        f.votes = {"code_check": {"confirmed": 3, "cast": 3, "errors": 0}}
        text = render_report(Blueprint(name="docparse", type="library", domain="parsing", stage="released"), [f], None,
                             {"confirmed": 1, "checked": 9, "observations": 4})
        self.assertIn("Exploitability: conditional (2/3 checks agree); attacker: untrusted_content; enters at lib.js:2", text)
        self.assertIn("Only if: the app passes request bodies", text)
        self.assertIn("Held in 3 of 3 checks against the code", text)
        self.assertIn("4 more were accurate about the code but are not exploitable", text)

    def test_a_finding_checked_once_without_exploitability_prints_neither_line(self):
        f = finding()
        text = render_report(Blueprint(name="docparse", type="library", domain="parsing", stage="released"), [f], None, None)
        self.assertNotIn("Exploitability:", text)
        self.assertNotIn("checks against the code", text)


if __name__ == "__main__":
    unittest.main()
