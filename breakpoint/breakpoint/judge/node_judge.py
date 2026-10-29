"""Run a Node proof against a library checkout and report what happened.

Nothing here asks a model. A proof "works" when, in a fresh Node process, it loads the library and
(oracle "pollution") leaves a new key on Object.prototype, or (oracle "crash") makes an uncaught error
whose stack runs through the library. To rule out proofs that do the damage themselves, the same proof is
run again with the library replaced by an empty stand-in (the control run); if the control run fires too,
the proof cheated.

Isolation is Node's permission flag (no writes, no child processes, reads only the library, the proof and
the harness) plus a soft network block inside the harness. That is not a hard boundary: run proofs you did
not write inside WSL or Docker.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

HARNESS = Path(__file__).with_name("harness.js")
MARKER = "@@JUDGE@@ "
ORACLES = ("pollution", "crash")

# What a proof must not reach for. Prototype writes are not listed on purpose: the control run catches them.
FORBIDDEN = [
    (r"\bimport\s*\(", "dynamic import"),
    (r"^\s*import\s", "ES module import"),
    (r"\beval\s*\(", "eval"),
    (r"\bnew\s+Function\b|\bFunction\s*\(", "Function constructor"),
    (r"process\s*\.\s*(binding|dlopen|mainModule|_linkedBinding|reallyExit|kill)", "process internals"),
    (
        r"require\s*\(\s*['\"](?:node:)?(child_process|worker_threads|vm|net|http|https|http2|dns|tls|dgram|"
        r"cluster|inspector|module|v8|wasi|repl)['\"]\s*\)",
        "restricted module",
    ),
]

# A proof that did nothing wrong but whose target refused it counts as the fix holding.
HOLD_REASONS = {"no_effect", "rejected_by_library"}


@dataclass
class Verdict:
    worked: bool
    reason: str
    oracle: str
    target_loaded: bool = False
    new_keys: list[str] = field(default_factory=list)
    crashed_in_target: bool = False
    control_fired: bool = False
    errors: list[str] = field(default_factory=list)
    output: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def forbidden_in(source: str) -> str | None:
    for pattern, label in FORBIDDEN:
        if re.search(pattern, source, re.MULTILINE):
            return label
    return None


def _run(repo: Path, proof: Path, oracle: str, mode: str, timeout: float) -> dict:
    node = shutil.which("node")
    if not node:
        return {"error": "node_not_found"}
    config = {"repo": str(repo), "proof": str(proof), "oracle": oracle, "mode": mode}
    env = {"BP_JUDGE_CONFIG": json.dumps(config), "PATH": str(Path(node).parent)}
    # Windows needs SystemRoot to start Node at all.
    for key in ("SystemRoot", "SYSTEMROOT", "TEMP", "TMP"):
        if key in os.environ:
            env[key] = os.environ[key]
    with tempfile.TemporaryDirectory(prefix="bp-judge-") as cwd:
        cmd = [
            node,
            "--permission",
            f"--allow-fs-read={repo}",
            f"--allow-fs-read={proof.parent}",
            f"--allow-fs-read={HARNESS.parent}",
            "--max-old-space-size=256",
            str(HARNESS),
        ]
        try:
            done = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"error": "timeout"}
    out, err = done.stdout or "", done.stderr or ""
    result = None
    shown = []
    for line in out.splitlines():
        if line.startswith(MARKER):
            try:
                result = json.loads(line[len(MARKER) :])
            except ValueError:
                pass
        else:
            shown.append(line)
    if result is None:
        return {"error": "no_result", "stderr": err[-1500:], "output": "\n".join(shown)[-1500:]}
    result["output"] = "\n".join(shown)[-1500:]
    result["stderr"] = err[-800:]
    return result


def _fired(result: dict, oracle: str) -> bool:
    if oracle == "pollution":
        return bool(result.get("newKeys"))
    return bool(result.get("crashFromTarget"))


def judge_proof(repo: str | Path, proof: str | Path, oracle: str = "pollution", timeout: float = 10.0) -> Verdict:
    if oracle not in ORACLES:
        raise ValueError(f"oracle must be one of {ORACLES}")
    repo, proof = Path(repo).resolve(), Path(proof).resolve()
    if not repo.is_dir():
        return Verdict(False, "repo_missing", oracle, detail=str(repo))
    if not proof.is_file():
        return Verdict(False, "proof_missing", oracle, detail=str(proof))
    blocked = forbidden_in(proof.read_text(encoding="utf-8", errors="replace"))
    if blocked:
        return Verdict(False, "forbidden_code", oracle, detail=blocked)

    real = _run(repo, proof, oracle, "real", timeout)
    if "error" in real:
        return Verdict(False, real["error"], oracle, output=real.get("output", ""), detail=real.get("stderr", ""))

    fired = _fired(real, oracle)
    errors = [f"{e.get('name')}: {e.get('message')}" for e in real.get("errors", [])]
    base = dict(
        oracle=oracle,
        target_loaded=bool(real.get("targetLoaded")),
        new_keys=real.get("newKeys", []),
        crashed_in_target=bool(real.get("crashFromTarget")),
        errors=errors,
        output=real.get("output", ""),
    )

    if not base["target_loaded"]:
        return Verdict(False, "library_not_used", **base)
    if not fired:
        if oracle == "pollution" and base["crashed_in_target"]:
            return Verdict(False, "rejected_by_library", **base)
        return Verdict(False, "proof_error" if errors and not base["crashed_in_target"] else "no_effect", **base)

    control = _run(repo, proof, oracle, "control", timeout)
    if "error" in control:
        return Verdict(False, "control_failed", detail=control["error"], **base)
    if _fired(control, oracle):
        return Verdict(False, "self_triggering", control_fired=True, **base)
    return Verdict(True, "worked", **base)


def check_pair(before: str | Path, after: str | Path, proof: str | Path, oracle: str = "pollution", timeout: float = 10.0) -> dict:
    """The proof must work on the vulnerable checkout and be stopped on the fixed one."""
    v_before = judge_proof(before, proof, oracle, timeout)
    v_after = judge_proof(after, proof, oracle, timeout)
    return {
        "ok": v_before.worked and v_after.reason in HOLD_REASONS,
        "before": v_before.to_dict(),
        "after": v_after.to_dict(),
    }
