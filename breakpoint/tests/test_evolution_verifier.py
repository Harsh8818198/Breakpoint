import json
import threading
import unittest

from breakpoint.evolution import simulate
from breakpoint.models import Agent, Blueprint

TITLES = ["Zebra lantern exploit", "Quantum river harvest", "Marble cactus overflow",
          "Violet engine bypass", "Orchid tunnel leakage", "Granite falcon replay",
          "Saffron mirror takeover", "Copper desert forgery"]


class ScriptedLLM:
    max_workers = 2

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def scale_tokens(self, base):
        return base

    def complete(self, system, user, *, task="", max_tokens=0):
        with self._lock:
            self.calls.append((task, user))
            n = len(self.calls)
        if task.startswith("finding_gen"):
            return json.dumps({"title": TITLES[n % len(TITLES)], "description": "d", "steps_to_exploit": ["s"],
                               "attack_category": "auth", "exploitability": 5, "impact_score": 5,
                               "spread": 5, "fix_difficulty": 1})
        if task == "crossover":
            return json.dumps({"name": f"Child{n}", "age": 30, "backstory": "b", "motivation": "m", "goal": "g"})
        raise AssertionError(f"unexpected task {task}")

    def prompts(self, task):
        return [u for t, u in self.calls if t == task]


def _setup():
    bp = Blueprint(name="X", type="app", domain="d", stage="live")
    agents = [Agent(name=n, archetype="A", age=30, backstory="b", motivation="m", goal="g")
              for n in ("Ann", "Ben")]
    return bp, agents


class VerifierInTheLoop(unittest.TestCase):
    def test_refuted_claims_do_not_carry_forward_but_are_shown_to_the_next_generation(self):
        bp, agents = _setup()
        llm, batches = ScriptedLLM(), []

        def verifier(findings):
            batches.append([f.title for f in findings])
            ok = len(batches) > 1  # reject everything in generation 1
            return [{"ok": ok, "evidence": f"observed 403 for {f.title}"} for f in findings]

        found = simulate(bp, agents, llm, generations=2, verifier=verifier)

        self.assertTrue(found and all(f.generation == 2 for f in found))
        gen1_titles = batches[0]
        gen2_prompts = "\n".join(llm.prompts("finding_gen2"))
        self.assertIn("ALREADY TESTED AND REFUTED", gen2_prompts)
        for t in gen1_titles:
            self.assertIn(f"observed 403 for {t}", gen2_prompts)
        self.assertNotIn("ALREADY TESTED AND REFUTED", "\n".join(llm.prompts("finding_gen1")))

    def test_without_a_verifier_everything_is_kept_as_before(self):
        bp, agents = _setup()
        llm = ScriptedLLM()
        found = simulate(bp, agents, llm, generations=2)
        self.assertEqual({f.generation for f in found}, {1, 2})
        self.assertNotIn("ALREADY TESTED AND REFUTED", "\n".join(u for _, u in llm.calls))


if __name__ == "__main__":
    unittest.main()
