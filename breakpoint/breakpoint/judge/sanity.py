"""Check the judge against real fixed bugs with hand-written proofs.

For each case the proof must work on the commit before the maintainers' fix and be stopped on the fix.
Folders: WORK/<name>/before and WORK/<name>/after, already installed and built (see judge_sanity/README.md).

    python -m breakpoint.judge.sanity --work WORK [--out results.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .node_judge import check_pair

PROOFS = Path(__file__).resolve().parents[2] / "judge_sanity" / "proofs"

CASES = {
    "scim": ("scim-patch.js", "pollution"),
    "i18next": ("i18next-fs-backend.js", "pollution"),
    "browserslist": ("browserslist.js", "crash"),
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--timeout", type=float, default=15.0)
    args = ap.parse_args(argv)

    results = {}
    for name, (proof, oracle) in CASES.items():
        pair = check_pair(args.work / name / "before", args.work / name / "after", PROOFS / proof, oracle, args.timeout)
        results[name] = pair
        b, a = pair["before"], pair["after"]
        print(f"{name:13} {oracle:9} before: {b['reason']:20} after: {a['reason']:20} -> {'OK' if pair['ok'] else 'FAIL'}")
    good = sum(1 for r in results.values() if r["ok"])
    print(f"\n{good} of {len(results)} cases: proof works before the fix and is stopped after it")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if good == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
