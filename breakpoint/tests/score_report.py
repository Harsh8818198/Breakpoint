"""How many of the 13 real NodeGoat bugs does a (verified) report contain? (no model calls)

    python -m tests.score_report report.json [--gold tests/fixtures/nodegoat_gold_locations.json]

`report.json` is what `python -m breakpoint.run --codebase <NodeGoat> --output report.json` writes, or what
`--verify-report baseline.json --codebase <NodeGoat> --output baseline_verified.json` writes. Only findings the code check
KEPT are scored (they carry `evidence`: real file:line quotes found in the repository).

A finding counts as finding a bug when one of its evidence lines falls inside that bug's known location. This is a mechanical
match on where the finding points, not on what it says, so it can be fooled both ways: it prints every match and every kept
finding that matched nothing, and those lists must be read by a person before the number is quoted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from breakpoint.evolution import _similar

HERE = os.path.dirname(__file__)
SLACK = 2        # lines of tolerance either side of a known location


def matches(finding: dict, bug: dict) -> list[str]:
    hits = []
    for e in finding.get("evidence") or []:
        for loc in bug["locations"]:
            lo, hi = loc["lines"]
            if e.get("file") == loc["file"] and lo - SLACK <= int(e.get("line", -99)) <= hi + SLACK:
                hits.append(f"{e['file']}:{e['line']}")
                break
    return hits


def score(report: dict, gold: list[dict], claims: list[dict]) -> dict:
    kept = [f for f in report.get("findings", []) if f.get("evidence")]
    per_bug = []
    for bug in gold:
        found_by = [(f["title"], matches(f, bug)) for f in kept if matches(f, bug)]
        per_bug.append({"title": bug["title"], "found_by": found_by})
    matched_titles = {t for b in per_bug for t, _ in b["found_by"]}
    unmatched = [f for f in kept if f["title"] not in matched_titles]
    false_claims = [c for c in claims if c["label"] == "false"]
    lookalikes = [(f["title"], c["title"]) for f in kept for c in false_claims if _similar(f["title"], c["title"], 0.35)]
    return {"kept": len(kept), "bugs": per_bug, "found": sum(1 for b in per_bug if b["found_by"]),
            "unmatched": unmatched, "lookalikes": lookalikes, "total": len(report.get("findings", []))}


def adjudicate(report: dict, gold: list[dict], adj: dict) -> dict:
    """Apply a person's verdicts ({finding title: {"verdict": real|false|mixed, "bug": gold title or null}}) to a report.
    This is the number to quote: the location match above can credit a finding for a bug it never claimed."""
    kept = [f for f in report.get("findings", []) if f.get("evidence")]
    verdicts = adj.get("verdicts", {})
    gold_titles = {b["title"] for b in gold}
    found: dict[str, list[str]] = {}
    unlabelled_real, wrong, undecided = [], [], []
    for f in kept:
        v = verdicts.get(f["title"])
        if v is None:
            undecided.append(f["title"])
        elif v["verdict"] == "real" and v.get("bug") in gold_titles:
            found.setdefault(v["bug"], []).append(f["title"])
        elif v["verdict"] == "real":
            unlabelled_real.append(f["title"])
        else:
            wrong.append((f["title"], v.get("note", "")))
    return {"kept": len(kept), "found": found, "unlabelled_real": unlabelled_real, "wrong": wrong, "undecided": undecided,
            "missed": [b["title"] for b in gold if b["title"] not in found]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--adjudication", help="JSON of hand verdicts for this report's kept findings (see adjudicate())")
    ap.add_argument("--gold", default=os.path.join(HERE, "fixtures", "nodegoat_gold_locations.json"))
    ap.add_argument("--claims", default=os.path.join(HERE, "fixtures", "nodegoat_labeled_claims.json"))
    args = ap.parse_args(argv)
    report = json.load(open(args.report, encoding="utf-8"))
    gold = json.load(open(args.gold, encoding="utf-8"))["bugs"]
    claims = json.load(open(args.claims, encoding="utf-8"))["findings"]
    r = score(report, gold, claims)
    v = report.get("verification") or {}
    if v:
        print(f"code check: {v.get('confirmed')} of {v.get('checked')} claims held up")
    if not r["kept"]:
        print("No finding in this report carries code evidence (was it checked against the code?).")
    for b in r["bugs"]:
        if b["found_by"]:
            t, locs = b["found_by"][0]
            more = f" (+{len(b['found_by']) - 1} more)" if len(b["found_by"]) > 1 else ""
            print(f"[FOUND ] {b['title']}\n          <- \"{t}\" at {', '.join(locs)}{more}")
        else:
            print(f"[missed] {b['title']}")
    print(f"\n{r['found']}/{len(gold)} real bugs found by the {r['kept']} findings the code check kept")
    if r["unmatched"]:
        print(f"\n{len(r['unmatched'])} kept finding(s) point somewhere else. READ THESE: each is either a real bug the label set "
              f"does not list, or a false claim that got through:")
        for f in r["unmatched"]:
            ev = f["evidence"][0]
            print(f"  - {f['title']}\n      {ev['file']}:{ev['line']}  {ev['quote'][:140]}")
    if r["lookalikes"]:
        print("\nKept findings whose title resembles a claim labelled FALSE (check by hand):")
        for t, c in r["lookalikes"]:
            print(f"  - \"{t}\"  ~  \"{c}\"")
    if args.adjudication:
        a = adjudicate(report, gold, json.load(open(args.adjudication, encoding="utf-8")))
        print(f"\n=== HAND-ADJUDICATED ({args.adjudication}) ===")
        print(f"{len(a['found'])}/{len(gold)} real bugs found; {len(a['unlabelled_real'])} further kept finding(s) are real but not in the "
              f"label set; {len(a['wrong'])} kept finding(s) are false or misleading; {a['kept']} kept in all")
        for bug, titles in a["found"].items():
            print(f"  [FOUND ] {bug}  <- {'; '.join(titles)}")
        for bug in a["missed"]:
            print(f"  [missed] {bug}")
        for t in a["unlabelled_real"]:
            print(f"  [real, unlabelled] {t}")
        for t, note in a["wrong"]:
            print(f"  [WRONG ] {t}: {note}")
        if a["undecided"]:
            print(f"  WARNING: no verdict yet for: {a['undecided']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
