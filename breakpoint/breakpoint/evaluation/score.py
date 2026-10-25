"""Score saved runs against an evaluation set, and say how much of the score to trust.

Two scores, kept apart on purpose:
  mechanical    a known bug counts as found when a kept finding's evidence line falls inside its location (2 lines of slack).
                Cheap and repeatable, but it can credit a finding for a bug it never claimed: in our first NodeGoat run it
                credited 13 of 13 where a person found 10.
  adjudicated   a person reads each distinct issue once and says real / false / mixed and which known bug it is. Verdicts are
                saved against an issue key, so the same issue seen in several runs and arms is judged once. Anything not yet
                judged is reported as undecided, never silently counted either way.

Findings are grouped into issues by where their evidence points (same file, within 2 lines) or, within one file, by a
similar title. Mixed counts as wrong.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..evolution import _norm, _similar
from .sets import Bug, EvalSet

SLACK = 2


def _evidence(f: dict) -> list[dict]:
    return [e for e in (f.get("evidence") or []) if isinstance(e, dict) and e.get("file") and e.get("line") is not None]


def bugs_hit(f: dict, bugs: list[Bug]) -> list[str]:
    """Ids of the known bugs this finding's evidence points into (mechanical match)."""
    ev, hits = _evidence(f), []
    for b in bugs:
        for loc in b.locations:
            lo, hi = loc["lines"]
            if any(e["file"] == loc["file"] and lo - SLACK <= int(e["line"]) <= hi + SLACK for e in ev):
                hits.append(b.id)
                break
    return hits


def load_runs(out_dir: Path, set_id: str, variant: str) -> list[dict]:
    runs = []
    for p in sorted((out_dir / f"{set_id}__{variant}").glob("*/run_*.json")):
        try:
            runs.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            print(f"[warn] skipping unreadable run file {p}")
    return runs


# --------------------------------------------------------------------------- issues (clusters of findings)
def _near(a: dict, b: dict) -> bool:
    return any(x["file"] == y["file"] and abs(int(x["line"]) - int(y["line"])) <= SLACK for x in _evidence(a) for y in _evidence(b))


def _primary_file(f: dict) -> str | None:
    ev = _evidence(f)
    return min((e["file"] for e in ev), default=None)


def cluster(items: list[tuple[dict, dict]]) -> list[dict]:
    """items: (run record, finding dict). Returns [{"key", "members": [(run, finding)]}] in key order."""
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i][1], items[j][1]
            similar = _similar(a.get("title", ""), b.get("title", ""), 0.6)
            same = _near(a, b) or (_primary_file(a) == _primary_file(b) and similar)    # two findings with no evidence share None
            if same:
                parent[find(j)] = find(i)
    groups: dict[int, list] = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)
    out = []
    for members in groups.values():
        locs = sorted((e["file"], int(e["line"])) for _, f in members for e in _evidence(f))
        key = f"{locs[0][0]}:{locs[0][1]}" if locs else "title:" + _norm(members[0][1].get("title", ""))[:40]
        out.append({"key": key, "members": members})
    return sorted(out, key=lambda c: c["key"])


def _all_kept(runs: list[dict]) -> list[tuple[dict, dict]]:
    return [(r, f) for r in runs if r.get("status") == "ok" for f in r.get("kept", [])]


def load_adjudication(path: Path | None) -> dict:
    """{key: {"verdict", "bug", "note"}} from a verdicts file, or from a filled-in todo file."""
    if path is None or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "verdicts" in data:
        return {k: v for k, v in data["verdicts"].items() if isinstance(v, dict) and v.get("verdict")}
    return {c["key"]: {"verdict": c["verdict"], "bug": c.get("bug"), "note": c.get("note", "")}
            for c in data.get("clusters", []) if c.get("verdict")}


def adjudication_todo(es: EvalSet, variant: str, runs: list[dict], existing: dict | None = None) -> dict:
    existing = existing or {}
    clusters = []
    for c in cluster(_all_kept(runs)):
        members = c["members"]
        titles = list(dict.fromkeys(f["title"] for _, f in members))[:6]
        seen = list(dict.fromkeys((r["arm"], r["run"]) for r, _ in members))
        prior = existing.get(c["key"], {})
        clusters.append({
            "key": c["key"], "titles": titles, "description": members[0][1].get("description", "")[:500],
            "evidence": _evidence(members[0][1])[:3],
            "seen_in": [{"arm": a, "run": n} for a, n in seen],
            "mechanical_bugs": sorted({b for _, f in members for b in bugs_hit(f, es.bugs)}),
            "verdict": prior.get("verdict"), "bug": prior.get("bug"), "note": prior.get("note", "")})
    return {"_about": (f"Issues kept by any arm on {es.id} [{variant}]. Fill 'verdict' with real, false or mixed (mixed counts as "
                       "wrong); for a real issue set 'bug' to the id of the known bug it is (a list of ids if one finding really "
                       "covers several), or leave it null if it is a real weakness the label set does not list. Read the code, not the title. Verdicts are keyed by 'key' and are "
                       "reused for every run and arm that produces the same issue."),
            "set": es.id, "variant": variant, "bug_ids": [b.id for b in es.bugs], "clusters": clusters}


# --------------------------------------------------------------------------- numbers
def _spread(vals: list[float]) -> dict:
    return {"mean": round(sum(vals) / len(vals), 3), "min": round(min(vals), 3), "max": round(max(vals), 3)} if vals else \
        {"mean": None, "min": None, "max": None}


def _bug_ids(verdict: dict) -> set[str]:
    """The known bugs a verdict says an issue is: one id, or a list when one finding really covers several."""
    b = verdict.get("bug")
    return {x for x in (b if isinstance(b, list) else [b]) if isinstance(x, str)}


def _checking(run: dict) -> str:
    """How a run's claims were checked. Runs saved before this was an option were checked once, with no exploitability step."""
    cfg = run.get("verify_config")
    if not cfg:
        return "checked once, no exploitability step (older run)"
    return f"checked up to {cfg['checks']} time(s) per claim" + (", then judged for exploitability" if cfg.get("exploit") else ", no exploitability step")


def _arm_summary(label: str, runs: list[dict], es: EvalSet, verdicts: dict, key_of: dict) -> dict:
    ok = [r for r in runs if r.get("status") == "ok"]
    out: dict = {"label": label, "runs": len(ok), "unsupported": [r.get("reason") for r in runs if r.get("status") == "unsupported"][:1],
                 "errored_runs": [r["run"] for r in runs if r.get("status") == "error"],
                 "verify": all(r.get("verify") for r in ok) if ok else None, "models": sorted({r["model"] for r in ok}),
                 "checking": sorted({_checking(r) for r in ok if r.get("verify")})}
    if not ok:
        return out
    n_bugs = len(es.bugs)
    found_sets = [{b for f in r["kept"] for b in bugs_hit(f, es.bugs)} for r in ok]
    kept_counts = [len(r["kept"]) for r in ok]
    matched = [(sum(1 for f in r["kept"] if bugs_hit(f, es.bugs)) / len(r["kept"])) if r["kept"] else 0.0 for r in ok]
    issues = [len({key_of[id(f)] for f in r["kept"]}) for r in ok]
    out["mechanical"] = {"found_per_run": [len(s) for s in found_sets], "recall": _spread([len(s) / n_bugs for s in found_sets]),
                         "found_in_any": sorted(set().union(*found_sets)), "found_in_all": sorted(set.intersection(*found_sets)),
                         "per_bug": {b.id: sum(b.id in s for s in found_sets) for b in es.bugs}}
    out["kept"] = _spread(kept_counts)
    out["issues"] = _spread(issues)
    out["matched_share"] = _spread(matched)
    if verdicts:
        per_run = []
        for r in ok:
            keys = {key_of[id(f)] for f in r["kept"]}
            found, real_other, wrong, undecided = set(), set(), set(), set()
            real_labelled = 0                                           # issues that are a known bug (one issue may cover several)
            for k in keys:
                v = verdicts.get(k)
                if v is None:
                    undecided.add(k)
                elif v["verdict"] == "real" and _bug_ids(v) & {b.id for b in es.bugs}:
                    found |= _bug_ids(v) & {b.id for b in es.bugs}
                    real_labelled += 1
                elif v["verdict"] == "real":
                    real_other.add(k)
                else:
                    wrong.add(k)
            decided = len(keys) - len(undecided)
            per_run.append({"found": found, "real_other": len(real_other), "wrong": len(wrong), "undecided": len(undecided),
                            "precision": ((real_labelled + len(real_other)) / decided) if decided else None,
                            "issues": len(keys)})
        # precision here is per distinct issue (a duplicate does not count twice); a bug counts once however many issues name it
        precs = [p["precision"] for p in per_run if p["precision"] is not None]
        out["adjudicated"] = {
            "complete": all(p["undecided"] == 0 for p in per_run),
            "found_per_run": [len(p["found"]) for p in per_run],
            "recall": _spread([len(p["found"]) / n_bugs for p in per_run]),
            "found_in_any": sorted(set().union(*[p["found"] for p in per_run])),
            "found_in_all": sorted(set.intersection(*[p["found"] for p in per_run])),
            "per_bug": {b.id: sum(b.id in p["found"] for p in per_run) for b in es.bugs},
            "precision": _spread(precs), "real_other": _spread([p["real_other"] for p in per_run]),
            "wrong": _spread([p["wrong"] for p in per_run]), "undecided": sum(p["undecided"] for p in per_run)}
    calls = [r["usage"]["arm"]["calls"] + r["usage"]["check"]["calls"] for r in ok]
    toks = [r["usage"]["arm"]["est_tokens"] + r["usage"]["check"]["est_tokens"] for r in ok]
    secs, slept = [], []
    for r in ok:
        calls_s = r["usage"]["arm"]["seconds_in_calls"] + r["usage"]["check"]["seconds_in_calls"]
        if r["seconds"]["total"] > 5 * calls_s + 60:          # the machine slept or stalled: the call time is the honest figure
            secs.append(calls_s)
            slept.append(r["run"])
        else:
            secs.append(r["seconds"]["total"])
    out["clock_anomaly_runs"] = slept
    best = out.get("adjudicated") if out.get("adjudicated", {}).get("complete") else out["mechanical"]
    mean_found = sum(best["found_per_run"]) / len(ok)
    out["cost"] = {"calls": _spread(calls), "est_tokens": _spread(toks), "seconds": _spread(secs),
                   "calls_per_bug_found": round((sum(calls) / len(ok)) / mean_found, 1) if mean_found else None,
                   "basis": "adjudicated" if best is out.get("adjudicated") else "mechanical"}
    return out


def summarize(es: EvalSet, variant: str, runs: list[dict], verdicts: dict | None = None) -> dict:
    verdicts = verdicts or {}
    items = _all_kept(runs)
    clusters = cluster(items)
    key_of = {id(f): c["key"] for c in clusters for _, f in c["members"]}
    by_arm: dict[str, list[dict]] = {}
    for r in runs:
        by_arm.setdefault(r["arm"], []).append(r)
    arms = {label: _arm_summary(label, rs, es, verdicts, key_of) for label, rs in sorted(by_arm.items())}
    undecided = sorted(c["key"] for c in clusters if verdicts and c["key"] not in verdicts)
    return {"set": es.id, "variant": variant, "role": es.role, "commit": es.repo.get("commit", ""), "bugs": [b.to_dict() for b in es.bugs],
            "arms": arms, "issues": len(clusters), "adjudicated": bool(verdicts), "undecided_issues": undecided,
            "flags": _flags(es, variant, arms, bool(verdicts), undecided)}


def _flags(es: EvalSet, variant: str, arms: dict, adjudicated: bool, undecided: list[str]) -> list[str]:
    flags = []
    if es.role == "dev":
        flags.append("DEV SET: this repository was used while building Breakpoint. Do not quote these numbers as held-out.")
    if es.contamination:
        flags.append(f"Contamination: {es.contamination}")
    if variant == "raw" and es.variants:
        flags.append("RAW variant: the repository may announce its own bugs in comments, docs or tutorials. Compare with a cleaned variant.")
    short = [a["label"] for a in arms.values() if a.get("runs", 0) and a["runs"] < 3]
    if short:
        flags.append(f"Fewer than 3 runs for {', '.join(short)}: run-to-run spread is not meaningful.")
    failed = {a["label"]: a["errored_runs"] for a in arms.values() if a.get("errored_runs")}
    if failed:
        flags.append("Run(s) whose model reply could not be read are not counted (not scored as misses): "
                     + "; ".join(f"{l} run(s) {r}" for l, r in failed.items()) + ". Run the evaluation again to retry them.")
    slept = {a["label"]: a["clock_anomaly_runs"] for a in arms.values() if a.get("clock_anomaly_runs")}
    if slept:
        flags.append("Wall-clock time for " + "; ".join(f"{l} run(s) {r}" for l, r in slept.items())
                     + " was far above the time spent in model calls (the machine probably slept); the call time is shown instead.")
    how = {a["label"]: a["checking"] for a in arms.values() if a.get("checking")}
    if how:
        flags.append("Code check: " + "; ".join(f"{l}: {' and '.join(c)}" for l, c in how.items()) + ".")
    if any(a.get("verify") is False for a in arms.values()):
        flags.append("Some arms were NOT checked against the code: their kept findings are claims, not proven.")
    if not adjudicated:
        flags.append("Mechanical scores only (location match). Not adjudicated: a person has not yet read the findings.")
    elif undecided:
        flags.append(f"{len(undecided)} issue(s) have no verdict yet; adjudicated numbers exclude them.")
    if es.provenance:
        flags.append(f"Labels: {es.provenance}")
    return flags


# --------------------------------------------------------------------------- rendering
def _fmt(s: dict | None, pct: bool = False, digits: int = 1) -> str:
    if not s or s.get("mean") is None:
        return "-"
    plain = lambda v: f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:.{digits}f}"        # noqa: E731
    f = (lambda v: f"{v * 100:.0f}%") if pct else plain
    return f(s["mean"]) if s["min"] == s["max"] else f"{f(s['mean'])} ({f(s['min'])} to {f(s['max'])})"


def render(summary: dict) -> str:
    n = len(summary["bugs"])
    L = [f"# {summary['set']} [{summary['variant']}]  ({n} known bugs, {summary['issues']} distinct issues kept across all runs)", ""]
    L += [f"- {f}" for f in summary["flags"]] + [""]
    L += ["| Arm | Runs | Bugs found (mechanical) | Bugs found (adjudicated) | Kept | Precision | Calls | Est. tokens | Seconds | Calls per bug found |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for label, a in summary["arms"].items():
        if not a.get("runs"):
            L.append(f"| {label} | 0 | {a.get('unsupported') or 'no completed runs'} |||||||")
            continue
        adj, mech = a.get("adjudicated"), a["mechanical"]
        precision = (_fmt(adj["precision"], pct=True) + ("" if adj["complete"] else " (incomplete)")) if adj else \
            f"{_fmt(a['matched_share'], pct=True)} matched a known bug (proxy)"
        L.append(f"| {label} | {a['runs']} | {_fmt({'mean': mech['recall']['mean'] * n, 'min': mech['recall']['min'] * n, 'max': mech['recall']['max'] * n})} of {n} "
                 f"| {(_fmt({'mean': adj['recall']['mean'] * n, 'min': adj['recall']['min'] * n, 'max': adj['recall']['max'] * n}) + ' of ' + str(n)) if adj else '-'} "
                 f"| {_fmt(a['kept'])} | {precision} | {_fmt(a['cost']['calls'], digits=0)} | {_fmt(a['cost']['est_tokens'], digits=0)} "
                 f"| {_fmt(a['cost']['seconds'], digits=0)} | {a['cost']['calls_per_bug_found'] if a['cost']['calls_per_bug_found'] is not None else '-'} ({a['cost']['basis']}) |")
    L += ["", "## Per known bug (runs that found it / runs)", ""]
    labels = [l for l, a in summary["arms"].items() if a.get("runs")]
    L += ["| Bug | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for b in summary["bugs"]:
        cells = []
        for l in labels:
            a = summary["arms"][l]
            src = a.get("adjudicated") or a["mechanical"]
            cells.append(f"{src['per_bug'][b['id']]}/{a['runs']}")
        L.append(f"| {b['title'][:70]} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("Estimated tokens are characters / 4. 'Mechanical' counts a bug as found when a kept finding's evidence line falls inside its "
             "location; only the adjudicated column reflects what the findings actually say.")
    return "\n".join(L)
