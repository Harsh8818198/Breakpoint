"""Score the code verifier on a repo whose answers are known (live model calls; not part of the unit suite).

    python -m tests.eval_verifier --codebase path/to/NodeGoat [--claims tests/fixtures/nodegoat_labeled_claims.json]

Prints, per labelled claim, whether the verifier agreed, then:
  recall           real claims it confirmed        (a high number means it does not throw away true bugs)
  false-accept     false claims it confirmed       (the number that must stay at zero for "everything reported works")
"""

from __future__ import annotations

import argparse
import json
import sys

from breakpoint.codeindex import CodeIndex
from breakpoint.codeverify import CodeVerifier
from breakpoint.llm import LLMClient
from breakpoint.run import _finding_from_dict


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codebase", required=True)
    ap.add_argument("--claims", default="tests/fixtures/nodegoat_labeled_claims.json")
    ap.add_argument("--no-defend", action="store_true")
    args = ap.parse_args(argv)

    data = json.load(open(args.claims, encoding="utf-8"))
    claims = data["findings"]
    findings = [_finding_from_dict(c) for c in claims]
    llm = LLMClient()
    print(f"{llm.provider}/{llm.model}: checking {len(findings)} labelled claims")
    verifier = CodeVerifier(CodeIndex.from_dir(args.codebase), llm, defend=not args.no_defend)
    results = verifier(findings)

    real_total = sum(c["label"] == "real" for c in claims)
    false_total = len(claims) - real_total
    hit = fa = 0
    for c, r in zip(claims, results):
        confirmed = r["status"] == "CONFIRMED"
        ok = confirmed == (c["label"] == "real")
        hit += c["label"] == "real" and confirmed
        fa += c["label"] == "false" and confirmed
        print(f"[{'ok ' if ok else 'BAD'}] label={c['label']:<5} verdict={r['status']:<10} {r['code']:<22} {c['title']}")
        if not ok:
            print("      " + r["evidence"][:330])
    print(f"\nrecall {hit}/{real_total} real claims confirmed | false-accept {fa}/{false_total} false claims confirmed")
    return 0 if fa == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
