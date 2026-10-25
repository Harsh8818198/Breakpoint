"""Run arms on an evaluation set, several times each, and save every run as it finishes.

One file per run: `<out>/<set>__<variant>/<arm>/run_<n>.json`. A run holds the kept findings with their evidence, what the
code check threw away and why, calls, estimated tokens and seconds for the arm and for the checking, and the model used.
A provider failure stops the whole evaluation but never loses a finished run, and `resume` skips runs already on disk.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from ..codeindex import CodeIndex
from ..codeverify import CodeVerifier
from ..llm import LLMClient
from ..usage import MeteredLLM
from .arms import ArmUnsupported, arm_label, run_arm
from .sets import EvalSet, materialize

SCHEMA = 1


def run_dir(out_dir: Path, es: EvalSet, variant: str) -> Path:
    return out_dir / f"{es.id}__{variant}"


def run_file(out_dir: Path, es: EvalSet, variant: str, arm: str, n: int) -> Path:
    return run_dir(out_dir, es, variant) / arm_label(arm) / f"run_{n}.json"


def _done(path: Path) -> bool:
    """A run file that holds a finished run. A run that failed to read the model's reply is done again on resume."""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("status") != "error"
    except (OSError, ValueError):
        return False


def _write(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    tmp.replace(path)                                   # a crash never leaves half a run behind


def one_run(es: EvalSet, variant: str, arm: str, n: int, root: str, index: CodeIndex, base_llm, *, verify: bool,
            opts: dict, verifier_factory=None) -> dict:
    arm_llm, check_llm = MeteredLLM(base_llm), MeteredLLM(base_llm)
    rec = {"schema": SCHEMA, "set": es.id, "variant": variant, "arm": arm_label(arm), "run": n,
           "commit": es.repo.get("commit", ""), "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "model": f"{base_llm.provider}/{base_llm.model}", "verify": bool(verify)}
    t0 = time.monotonic()
    try:
        result = run_arm(arm, root, index, arm_llm, opts)
    except ArmUnsupported as e:
        return {**rec, "status": "unsupported", "reason": str(e)}
    t_arm = time.monotonic() - t0
    if result.meta.get("error") and not result.findings:
        # the model's reply could not be read: that is a failed run, not a run that found nothing, and must not be scored as a miss
        return {**rec, "status": "error", "reason": result.meta["error"], "seconds": {"arm": round(t_arm, 1)},
                "usage": {"arm": arm_llm.meter.snapshot()}}
    kept, stats, rejected = result.findings, None, []
    t1 = time.monotonic()
    # every finding the arm proposed and what the check did with it, so "did it propose the known flaw, and did the check keep it" can be asked
    proposed = [{"title": f.title, "code_refs": list(f.code_refs), "outcome": "unchecked"} for f in result.findings]
    if verify and result.findings:
        verifier = (verifier_factory or CodeVerifier)(index, check_llm)
        outcome = verifier(result.findings)
        kept = []
        for f, r, p in zip(result.findings, outcome, proposed):
            p["outcome"] = "kept" if r["status"] == "CONFIRMED" else f"{r['status']}:{r.get('code', '')}"
            if r["status"] == "CONFIRMED":
                f.verification, f.evidence = "CONFIRMED", r["evidence_items"]
                kept.append(f)
        stats = verifier.stats()
        rejected = [{"title": r["title"], "status": r["status"], "code": r["code"], "why": r.get("why", "")}
                    for r in stats.pop("rejected", [])]
    elif not verify:
        for f in result.findings:                       # unchecked: where the arm POINTS is all there is to score
            f.evidence = list(f.code_refs)
    t_check = time.monotonic() - t1
    return {**rec, "status": "ok", "candidates": len(result.findings), "kept": [f.to_dict() for f in kept],
            "proposed": proposed, "rejected": rejected, "verification": stats, "arm_meta": result.meta,
            "seconds": {"arm": round(t_arm, 1), "check": round(t_check, 1), "total": round(t_arm + t_check, 1)},
            "usage": {"arm": arm_llm.meter.snapshot(), "check": check_llm.meter.snapshot()}}


def run_eval(es: EvalSet, variant: str, arms: list[str], runs: int, out_dir: Path, cache_dir: Path, *, verify: bool = True,
             opts: dict | None = None, resume: bool = True, llm=None, verifier_factory=None, log=print) -> list[Path]:
    """Returns the run files, in order. Raises LLMFatalError (after saving what finished) if the provider gives up."""
    root = str(materialize(es, variant, cache_dir))
    index = CodeIndex.from_dir(root)
    base = llm or LLMClient()
    log(f"{es.id} [{variant}]: {len(index)} files, model {base.provider}/{base.model}, {runs} run(s) per arm, "
        f"{'with' if verify else 'WITHOUT'} the code check")
    files: list[Path] = []
    for arm in arms:
        for n in range(1, (1 if arm.startswith("import:") else runs) + 1):
            path = run_file(out_dir, es, variant, arm, n)
            files.append(path)
            if resume and path.exists() and _done(path):
                log(f"  {arm_label(arm)} run {n}: already on disk, skipped")
                continue
            log(f"  {arm_label(arm)} run {n} ...")
            rec = one_run(es, variant, arm, n, root, index, base, verify=verify, opts=opts or {}, verifier_factory=verifier_factory)
            _write(path, rec)
            if rec["status"] == "ok":
                u = rec["usage"]
                log(f"    {rec['candidates']} candidates -> {len(rec['kept'])} kept | {u['arm']['calls'] + u['check']['calls']} calls, "
                    f"~{u['arm']['est_tokens'] + u['check']['est_tokens']:,} tokens, {rec['seconds']['total']:.0f}s")
            else:
                log(f"    {rec['status']}: {rec.get('reason', '')}" + ("  (run the command again to retry it)" if rec["status"] == "error" else ""))
    return files
