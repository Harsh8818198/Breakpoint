"""One table over many advisory sets: for each fix-commit set, did the finder propose the known flaw, did the code check keep it,
and what else did the check let through.

The advisory sets (`eval_sets/history/<ghsa>/set.json`) each hold a single known flaw, so a per-set result is yes or no and only
the total over many sets means something. Three questions are kept apart:

  proposed   the arm's raw candidate list pointed into the fix's lines (before the code check; mechanical)
  kept       a finding that survived the code check points there (mechanical, and adjudicated when verdicts exist)
  other      what else was kept: real weaknesses the advisory does not name, and wrong claims (needs a person's verdicts)

"proposed but not kept" is a flaw the code check threw away. "kept" with no adjudication is a location match, not proof.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import score
from .runner import run_dir
from .sets import SETS_DIR, EvalSet, load_set


def history_sets(sets_dir: Path | None = None) -> list[EvalSet]:
    d = sets_dir or (SETS_DIR / "history")
    return [load_set(str(p)) for p in sorted(d.glob("*/set.json"))] if d.is_dir() else []


def _proposed_hit(run: dict, es: EvalSet) -> bool | None:
    if "proposed" not in run:
        return None                                              # a run saved before candidates were recorded
    return any(score.bugs_hit({"evidence": p.get("code_refs") or []}, es.bugs) for p in run["proposed"])


def _reading(out_dir: Path) -> dict:
    """A person's verdicts on what each run proposed: `<out>/proposed_read.json`, {set: {"verdicts": ["Y"|"P"|"N", ...]}} in run order.
    Y: a candidate describes the advisory's flaw. P: right place and class, different or vaguer mechanism. N: none does."""
    p = Path(out_dir) / "proposed_read.json"
    try:
        return {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if isinstance(v, dict) and v.get("verdicts")}
    except (OSError, ValueError):
        return {}


def summarize_history(sets: list[EvalSet], out_dir: Path, variant: str = "raw", arm: str = "plain") -> dict:
    rows, not_run = [], []
    reading = _reading(out_dir)
    for es in sets:
        runs = [r for r in score.load_runs(out_dir, es.id, variant) if r.get("arm") == arm and r.get("status") == "ok"]
        if not runs:
            not_run.append(es.id)
            continue
        verdicts = score.load_adjudication(run_dir(out_dir, es, variant) / "adjudication.json")
        a = score.summarize(es, variant, runs, verdicts)["arms"][arm]
        proposed = [_proposed_hit(r, es) for r in runs]
        adj = a.get("adjudicated")
        said = reading.get(es.id, {}).get("verdicts") or []
        by_run = [said[r["run"] - 1] if 0 < r["run"] <= len(said) else None for r in runs]
        read = {"yes": by_run.count("Y"), "partial": by_run.count("P"), "no": by_run.count("N"),
                "unread": by_run.count(None)} if said else None
        rows.append({
            "set": es.id, "title": es.title, "runs": len(runs), "history": es.history, "read": read,
            "class": es.bugs[0].cls, "proposed": None if None in proposed else sum(proposed),
            "kept_mechanical": a["mechanical"]["found_per_run"], "kept_adjudicated": adj["found_per_run"] if adj else None,
            "adjudication_complete": bool(adj and adj["complete"]), "kept": a["kept"],
            "real_other": adj["real_other"] if adj else None, "wrong": adj["wrong"] if adj else None,
            "undecided": adj["undecided"] if adj else None, "calls": a["cost"]["calls"],
            "candidates": [r["candidates"] for r in runs]})
    return {"variant": variant, "arm": arm, "rows": rows, "not_run": not_run, "totals": _totals(rows)}


def _totals(rows: list[dict]) -> dict:
    runs = sum(r["runs"] for r in rows)
    proposed = [r["proposed"] for r in rows]
    adjudicated_ok = [r for r in rows if r["adjudication_complete"]]
    read = [r["read"] for r in rows if r["read"] and not r["read"]["unread"]]
    return {
        "sets": len(rows), "set_runs": runs,
        "read": {"sets": len(read), "runs": sum(sum(x.values()) for x in read), "yes": sum(x["yes"] for x in read),
                 "partial": sum(x["partial"] for x in read), "sets_with_yes": sum(1 for x in read if x["yes"]),
                 "sets_with_yes_or_partial": sum(1 for x in read if x["yes"] or x["partial"])} if read else None,
        "proposed": sum(p for p in proposed if p is not None) if None not in proposed else None,
        "kept_mechanical": sum(sum(r["kept_mechanical"]) for r in rows),
        "kept_adjudicated": sum(sum(r["kept_adjudicated"]) for r in adjudicated_ok) if adjudicated_ok else None,
        "adjudicated_sets": len(adjudicated_ok),
        "kept_issues_total": round(sum(r["kept"]["mean"] * r["runs"] for r in rows)),
        "calls_total": round(sum(r["calls"]["mean"] * r["runs"] for r in rows))}


def render(summary: dict, sets: list[EvalSet]) -> str:
    rows, t = summary["rows"], summary["totals"]
    reviews = [s.history.get("label_review", "") for s in sets]
    L = [f"# Advisory sets: {summary['arm']} arm [{summary['variant']}]  ({t['sets']} sets, {t['set_runs']} runs)", ""]
    L += ["- Each set is one advisory: the repository one commit before the maintainers' fix, labelled by the lines the fix changed.",
          "- 'Location' = a candidate's cited lines fall in the lines the fix changed (before the code check; over-credits and under-credits). "
          "'Read yes / partial' = a person read the candidates: yes describes the advisory's flaw, partial is the right place and class with "
          "a different or vaguer mechanism. 'Kept (read)' = the same judgement on findings that survived the code check. Trust the read columns.",
          "- One flaw per set: a single set says little, the total over many sets says something. Every advisory in the selection log "
          "(selection.json) is counted, not only the ones that worked."]
    unreviewed = sum(1 for x in reviews if "not reviewed" in x)
    if unreviewed:
        L.append(f"- {unreviewed} of {len(sets)} sets have a label nobody has checked against the advisory text.")
    if any(r["runs"] < 3 for r in rows):
        L.append("- Fewer than 3 runs per set: run-to-run spread is not measured.")
    if any(not r["adjudication_complete"] for r in rows):
        L.append("- Some sets are not fully read yet: adjudicated columns count only fully read sets.")
    L += ["", "| Advisory | Package | Class | Candidates | Location | Read yes | Read partial | Kept (location) | Kept (read) | Kept | Real other | Wrong | Calls |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def cell(x, runs, ok=True):
        return "-" if x is None or not ok else (f"{sum(x) if isinstance(x, list) else x}/{runs}")

    for r in rows:
        h = r["history"]
        rd = r["read"]
        L.append(f"| {r['set']} | {h.get('package', '')} | {r['class']} | {sum(r['candidates']) // r['runs']} | {cell(r['proposed'], r['runs'])} "
                 f"| {cell(rd['yes'], r['runs'], not rd['unread']) if rd else '-'} | {cell(rd['partial'], r['runs'], not rd['unread']) if rd else '-'} "
                 f"| {cell(r['kept_mechanical'], r['runs'])} | {cell(r['kept_adjudicated'], r['runs'], r['adjudication_complete'])} "
                 f"| {score._fmt(r['kept'])} | {score._fmt(r['real_other']) if r['real_other'] else '-'} "
                 f"| {score._fmt(r['wrong']) if r['wrong'] else '-'} | {score._fmt(r['calls'], digits=0)} |")
    n = t["set_runs"]
    if t["read"]:
        x = t["read"]
        L += ["", f"**Read by a person ({x['sets']} sets, {x['runs']} runs):** a candidate described the advisory's flaw in {x['yes']}/{x['runs']} runs "
                  f"(strict), and described it or was in the right place and class in {x['yes'] + x['partial']}/{x['runs']} (lenient). "
                  f"By set: {x['sets_with_yes']} of {x['sets']} sets strict, {x['sets_with_yes_or_partial']} of {x['sets']} lenient, "
                  f"in at least one of their runs."]
    L += ["", f"**Total over {t['sets']} sets ({n} runs):** location match {t['proposed'] if t['proposed'] is not None else '-'}/{n}; "
              f"kept by location {t['kept_mechanical']}/{n}; "
              + (f"kept and read as the flaw {t['kept_adjudicated']}/{sum(r['runs'] for r in rows if r['adjudication_complete'])} "
                 f"({t['adjudicated_sets']} fully read sets); " if t["kept_adjudicated"] is not None else "not yet read by a person; ")
              + f"{t['kept_issues_total']} findings kept in all, about {t['calls_total']} model calls."]
    if summary["not_run"]:
        L.append(f"\nNot run yet: {', '.join(summary['not_run'])}")
    return "\n".join(L)
