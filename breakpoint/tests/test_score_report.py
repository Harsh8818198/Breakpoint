import json
import os
import unittest

from .score_report import HERE, adjudicate, matches, score

GOLD = json.load(open(os.path.join(HERE, "fixtures", "nodegoat_gold_locations.json"), encoding="utf-8"))["bugs"]
CLAIMS = json.load(open(os.path.join(HERE, "fixtures", "nodegoat_labeled_claims.json"), encoding="utf-8"))["findings"]


def kept(title, file, line):
    return {"title": title, "evidence": [{"file": file, "line": line, "quote": "q"}]}


class Scoring(unittest.TestCase):
    def test_the_two_fixtures_describe_the_same_thirteen_bugs(self):
        real = [c["title"] for c in CLAIMS if c["label"] == "real"]
        self.assertEqual(real, [b["title"] for b in GOLD])
        self.assertEqual(len(real), 13)

    def test_a_finding_counts_only_where_its_evidence_points_at_the_known_location(self):
        eval_bug = GOLD[0]
        self.assertTrue(matches(kept("x", "app/routes/contributions.js", 32), eval_bug))
        self.assertTrue(matches(kept("x", "app/routes/contributions.js", 34 + 2), eval_bug))        # slack
        self.assertFalse(matches(kept("x", "app/routes/contributions.js", 60), eval_bug))
        self.assertFalse(matches(kept("x", "app/routes/other.js", 32), eval_bug))
        self.assertFalse(matches({"title": "x", "evidence": []}, eval_bug))

    def test_score_counts_bugs_lists_unmatched_findings_and_flags_lookalikes_of_false_claims(self):
        report = {"findings": [kept("Remote code execution through eval of amounts", "app/routes/contributions.js", 32),
                               kept("Open redirect on learn", "app/routes/index.js", 72),
                               kept("Something in the logging", "app/routes/error.js", 5),
                               kept("SQL injection in the login query", "app/data/user-dao.js", 100),
                               {"title": "no evidence at all", "evidence": []}]}
        r = score(report, GOLD, CLAIMS)
        self.assertEqual((r["found"], r["kept"]), (2, 4))
        self.assertEqual({f["title"] for f in r["unmatched"]}, {"Something in the logging", "SQL injection in the login query"})
        self.assertEqual(r["lookalikes"], [("SQL injection in the login query", "SQL injection in the login query")])


    def test_hand_verdicts_override_the_location_match(self):
        """A finding about the cookie secret that happens to cite server.js:82 must not be credited with the CSRF bug."""
        report = {"findings": [kept("Predictable session secret", "server.js", 82),
                               kept("Chained redirect to admin", "app/routes/index.js", 55),
                               kept("Weak thing", "config/config.js", 13),
                               kept("Not yet judged", "app/routes/index.js", 72)]}
        adj = {"verdicts": {
            "Predictable session secret": {"verdict": "real", "bug": "Hard-coded session signing secret"},
            "Chained redirect to admin": {"verdict": "false", "note": "both routes need login"},
            "Weak thing": {"verdict": "real", "bug": None}}}
        loc = score(report, GOLD, CLAIMS)
        self.assertGreaterEqual(loc["found"], 3)                                  # the location match credits several bugs...
        a = adjudicate(report, GOLD, adj)
        self.assertEqual(list(a["found"]), ["Hard-coded session signing secret"])  # ...the hand verdict credits one
        self.assertEqual(a["unlabelled_real"], ["Weak thing"])
        self.assertEqual([t for t, _ in a["wrong"]], ["Chained redirect to admin"])
        self.assertEqual(a["undecided"], ["Not yet judged"])
        self.assertEqual(len(a["missed"]), 12)


if __name__ == "__main__":
    unittest.main()
