"""How much of the known-bug code do the agents get to see? (no model calls, no key needed)

    python -m tests.eval_retrieval --codebase path/to/NodeGoat [--agents 10] [--gens 1]

Plans the attack category of every agent exactly as a run would, retrieves the code each agent would be shown, and checks
for each of the 13 real bugs whether its lines were in front of at least one agent. This measures the retrieval alone; it
says nothing about whether the agent then writes the finding, or whether the verifier keeps it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from breakpoint.codeindex import CodeIndex
from breakpoint.coderetrieval import CodeRetriever

HERE = os.path.dirname(__file__)


def shown_lines(retrievals) -> dict[str, set[int]]:
    seen: dict[str, set[int]] = {}
    for r in retrievals:
        for reg in r.regions:
            seen.setdefault(reg.path, set()).update(range(reg.start, reg.end + 1))
    return seen


def bug_seen(bug: dict, seen: dict[str, set[int]], index: CodeIndex) -> bool:
    """True if every... at least the first line range of some listed location is shown (any one location is enough)."""
    for loc in bug["locations"]:
        path = index.resolve_path(loc["file"])
        if not path:
            continue
        lo, hi = loc["lines"]
        hi = min(hi, len(index.lines(path)))
        # the lines that matter must be on screen; for a wide range require the first 40% of it
        need = range(lo, lo + max(1, (hi - lo + 1) * 2 // 5))
        if all(n in seen.get(path, ()) for n in need):
            return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codebase", required=True)
    ap.add_argument("--gold", default=os.path.join(HERE, "fixtures", "nodegoat_gold_locations.json"))
    ap.add_argument("--agents", type=int, default=10)
    ap.add_argument("--budget", type=int, default=22000)
    args = ap.parse_args(argv)

    index = CodeIndex.from_dir(args.codebase)
    retriever = CodeRetriever(index, budget_chars=args.budget)
    gold = json.load(open(args.gold, encoding="utf-8"))["bugs"]
    cats = retriever.plan_categories(args.agents, [])
    retrievals = retriever.assign(cats, [])
    print(f"{len(index)} source files indexed; strong regions per category: "
          + ", ".join(f"{c}={n}" for c, n in retriever.summary().items() if n))
    print("generation-1 plan:", ", ".join(f"{c}x{cats.count(c)}" for c in dict.fromkeys(cats)))
    sizes = [len(r.text) for r in retrievals]
    print(f"code shown per agent: {min(sizes)}-{max(sizes)} characters (about {max(sizes) // 4} tokens at most)")
    seen = shown_lines(retrievals)
    hit = 0
    for bug in gold:
        ok = bug_seen(bug, seen, index)
        hit += ok
        who = [f"{c}#{i}" for i, (c, r) in enumerate(zip(cats, retrievals)) if bug_seen(bug, shown_lines([r]), index)]
        print(f"[{'seen' if ok else 'MISSED':<6}] {bug['title']}" + (f"   <- shown to: {', '.join(who)}" if who else ""))
    print(f"\n{hit}/{len(gold)} real bugs had their code in front of at least one generation-1 agent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
