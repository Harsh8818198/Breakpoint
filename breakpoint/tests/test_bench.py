import unittest

from breakpoint.bench.exploits import DECOYS, REFERENCE_EXPLOITS
from breakpoint.bench.noteshare import ALL_FLAWS, FLAWS
from breakpoint.bench.spec import FLAW_OF_CLAIM
from breakpoint.bench.verify import CONFIRMED, INVALID, NOT_REPRODUCED, run_script, score


class VerifierDiscriminates(unittest.TestCase):
    def test_every_reference_exploit_confirms_on_the_flawed_app(self):
        for flaw, script in REFERENCE_EXPLOITS.items():
            with self.subTest(flaw=flaw):
                r = run_script(script)
                self.assertEqual(r.status, CONFIRMED, r.error)
                self.assertIn(flaw, {FLAW_OF_CLAIM.get(v.claim) for v in r.violations})

    def test_each_exploit_fails_once_its_flaw_is_patched(self):
        for flaw, script in REFERENCE_EXPLOITS.items():
            with self.subTest(flaw=flaw):
                self.assertEqual(run_script(script, ALL_FLAWS - {flaw}).status, NOT_REPRODUCED)

    def test_exploits_only_confirm_against_their_own_flaw(self):
        for enabled in FLAWS:
            for flaw, script in REFERENCE_EXPLOITS.items():
                with self.subTest(enabled=enabled, exploit=flaw):
                    expected = CONFIRMED if flaw == enabled else NOT_REPRODUCED
                    self.assertEqual(run_script(script, {enabled}).status, expected)

    def test_decoys_never_confirm_even_on_the_fully_flawed_app(self):
        for name, script in DECOYS.items():
            with self.subTest(decoy=name):
                r = run_script(script)
                self.assertEqual(r.status, NOT_REPRODUCED, [v.detail for v in r.violations])

    def test_patched_app_survives_every_exploit_and_decoy(self):
        for name, script in {**REFERENCE_EXPLOITS, **DECOYS}.items():
            with self.subTest(script=name):
                self.assertEqual(run_script(script, frozenset()).status, NOT_REPRODUCED)


class MalformedScripts(unittest.TestCase):
    def test_invalid_scripts_are_reported_not_crashed(self):
        bad = {
            "empty": [],
            "not a list": {"method": "GET"},
            "unresolved variable": [{"as": "bob", "method": "GET", "path": "/s/{nope}"}],
            "bad method": [{"as": "bob", "method": "TRACE", "path": "/notes/1"}],
            "relative path": [{"as": "bob", "method": "GET", "path": "notes/1"}],
            "too long": [{"as": "bob", "method": "GET", "path": "/notes/1"}] * 51,
            "unhashable field": [{"as": "alice", "method": "POST", "path": "/notes/1/share",
                                  "body": {"user": ["carol"]}}],
        }
        for name, script in bad.items():
            with self.subTest(case=name):
                self.assertEqual(run_script(script).status, INVALID)


class Scoring(unittest.TestCase):
    def test_precision_and_recall(self):
        results = [run_script(s) for s in [*REFERENCE_EXPLOITS.values(), *DECOYS.values()]]
        s = score(results)
        self.assertEqual(s["submitted"], 9)
        self.assertEqual(s["confirmed"], 4)
        self.assertEqual(s["precision"], round(4 / 9, 3))
        self.assertEqual(s["recall"], 1.0)
        self.assertEqual(s["flaws_found"], sorted(FLAWS))

    def test_no_findings_scores_zero(self):
        self.assertEqual(score([])["recall"], 0.0)
        self.assertEqual(score([])["precision"], 0.0)


if __name__ == "__main__":
    unittest.main()
