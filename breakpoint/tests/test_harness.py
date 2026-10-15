import json
import unittest

from breakpoint.bench.harness import OFF_TARGET, UNTESTABLE, evaluate, summarize


class FakeLLM:
    """Stands in for the model: returns whatever translator reply the test queues."""
    max_workers = 1

    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, *args, **kwargs):
        return self.replies.pop(0)


def reply(script, rule):
    return json.dumps({"script": script, "rule": rule})


BOB_READS_1 = [{"as": "bob", "method": "GET", "path": "/notes/1"}]
BOB_READS_2 = [{"as": "bob", "method": "GET", "path": "/notes/2"}]
CLAIM = {"title": "t", "description": "d", "steps": ["s"], "generation": 1}


class Harness(unittest.TestCase):
    def test_real_claim_is_confirmed_and_credited_to_its_flaw(self):
        row = evaluate([CLAIM], FakeLLM([reply(BOB_READS_1, "READ_AUTHZ")]))[0]
        self.assertEqual(row["status"], "CONFIRMED")
        self.assertEqual(row["flaws"], ["IDOR_READ"])

    def test_made_up_claim_is_not_real(self):
        row = evaluate([CLAIM], FakeLLM([reply(BOB_READS_2, "READ_AUTHZ")]))[0]
        self.assertEqual(row["status"], "NOT_REPRODUCED")

    def test_no_credit_when_the_script_breaks_a_rule_the_claim_never_named(self):
        row = evaluate([CLAIM], FakeLLM([reply(BOB_READS_1, "QUOTA")]))[0]
        self.assertEqual(row["status"], OFF_TARGET)
        self.assertEqual(row["flaws"], [])

    def test_bad_model_replies_become_untestable_not_a_crash(self):
        for raw in ['{"script": null}', "not json at all", "[1, 2]"]:
            with self.subTest(reply=raw):
                self.assertEqual(evaluate([CLAIM], FakeLLM([raw]))[0]["status"], UNTESTABLE)

    def test_summary_counts_and_generations(self):
        rows = evaluate([CLAIM, {**CLAIM, "generation": 2}, {**CLAIM, "generation": 2}, {**CLAIM, "generation": 2}],
                        FakeLLM([reply(BOB_READS_1, "READ_AUTHZ"), reply(BOB_READS_2, "READ_AUTHZ"),
                                 "garbage", reply(BOB_READS_1, "QUOTA")]))
        s = summarize(rows)
        self.assertEqual((s["claims"], s["tested"], s["real"], s["untestable"], s["off_target"]), (4, 3, 1, 1, 1))
        self.assertEqual(s["real_share_of_tested"], round(1 / 3, 2))
        self.assertEqual(s["planted_found"], ["IDOR_READ"])
        self.assertEqual(s["by_generation"][2], {"claims": 3, "tested": 2, "real": 0})


if __name__ == "__main__":
    unittest.main()
