"""The things being compared. Each arm turns a repository into a list of candidate findings; the runner then puts every
arm's candidates through the same code check, so an arm cannot win by being easier to believe.

  plain         one prompt with as much of the source as fits, asked once for the 15 worst vulnerabilities (baseline B1)
  route-review  the per-route review (Express apps only)
  import:<file> findings produced elsewhere, such as a saved Claude Code `/security-review`, Codex Security, Semgrep or
                CodeQL result (our JSON, or SARIF 2.1.0). This is how an agentic assistant (B2) or a static analyser (B3) is
                compared without this project having to run it.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..baseline import build_baseline
from ..codeindex import CodeIndex
from ..models import Finding
from ..routemap import map_routes
from ..routereview import review


class ArmUnsupported(Exception):
    """This arm cannot run on this repository (for example route review on a non-Express app)."""


@dataclass
class ArmResult:
    findings: list[Finding]
    meta: dict = field(default_factory=dict)


def _finding(d: dict) -> Finding:
    from ..run import _finding_from_dict          # imported late: run.py pulls in the whole engine
    return _finding_from_dict(d)


def run_plain(root: str, index: CodeIndex, llm, opts: dict) -> ArmResult:
    with contextlib.redirect_stdout(io.StringIO()):          # the baseline prints progress lines; the runner has its own
        try:
            data = build_baseline(root, llm, context="code", n=opts.get("n", 15))
        except ValueError as e:                              # the model returned nothing usable: an honest empty result
            return ArmResult([], {"error": str(e)})
    return ArmResult([_finding(d) for d in data["findings"]], {"baseline": data["baseline"]})


def run_route_review(root: str, index: CodeIndex, llm, opts: dict) -> ArmResult:
    rm = map_routes(index)
    if rm.framework is None:
        raise ArmUnsupported("route review reads Express apps only and found none in this repository")
    res = review(index, llm, rm, max_calls=opts.get("max_calls", 150), log=lambda *_: None)
    return ArmResult(res.findings, {"routes": len(rm.routes), "reviews": len(res.tasks), "candidates_before_merge": res.candidates,
                                    "errors": res.errors, "skipped_by_cap": res.skipped_by_cap})


ARMS = {"plain": run_plain, "route-review": run_route_review}


def arm_label(arm: str) -> str:
    return "import-" + re.sub(r"\W+", "_", Path(arm[len("import:"):]).stem) if arm.startswith("import:") else arm


# --------------------------------------------------------------------------- importing findings made elsewhere
def _rel(index: CodeIndex, uri: str) -> str:
    u = re.sub(r"^file:/+", "", uri or "").replace("\\", "/")
    return index.resolve_path(u) or u


def _quote_at(index: CodeIndex, path: str, line: int) -> str:
    if index.has(path) and 1 <= line <= len(index.lines(path)):
        return " ".join(index.lines(path)[line - 1].split())[:240]
    return ""


def from_sarif(data: dict, index: CodeIndex) -> list[Finding]:
    out: list[Finding] = []
    for run in data.get("runs", []):
        rules = {r.get("id"): r for r in (run.get("tool", {}).get("driver", {}).get("rules") or [])}
        for res in run.get("results", []):
            rule = rules.get(res.get("ruleId"), {})
            msg = (res.get("message") or {}).get("text", "")
            title = ((rule.get("shortDescription") or {}).get("text") or res.get("ruleId") or msg[:80] or "finding").strip()
            refs = []
            for loc in res.get("locations", [])[:3]:
                phys = loc.get("physicalLocation", {})
                path = _rel(index, (phys.get("artifactLocation") or {}).get("uri", ""))
                line = int((phys.get("region") or {}).get("startLine") or 0)
                if path and line:
                    refs.append({"file": path, "line": line, "quote": _quote_at(index, path, line)})
            out.append(Finding(title=title, generation=1, discovered_by="imported (SARIF)", description=msg,
                               attack_category=str(res.get("ruleId", "")), code_refs=refs))
    return out


def import_findings(path: str, index: CodeIndex) -> list[Finding]:
    """Our report JSON (`findings` list), a bare list of finding objects, or SARIF 2.1.0."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read findings from {path!r}: {e}") from None
    if isinstance(data, dict) and "runs" in data:
        return from_sarif(data, index)
    items = data.get("findings", []) if isinstance(data, dict) else data
    out = []
    for d in items if isinstance(items, list) else []:
        if not isinstance(d, dict) or not d.get("title"):
            continue
        d = dict(d, generation=d.get("generation", 1), discovered_by=d.get("discovered_by") or "imported",
                 description=d.get("description") or "")
        if not d.get("code_refs") and d.get("file") and d.get("line"):          # the minimal hand-written shape
            f = _rel(index, str(d["file"]))
            d["code_refs"] = [{"file": f, "line": int(d["line"]), "quote": _quote_at(index, f, int(d["line"]))}]
        out.append(_finding(d))
    return out


def run_import(arm: str, root: str, index: CodeIndex, llm, opts: dict) -> ArmResult:
    path = arm[len("import:"):]
    findings = import_findings(path, index)
    return ArmResult(findings, {"imported_from": path, "note": "produced elsewhere; not repeatable by this harness"})


def run_arm(arm: str, root: str, index: CodeIndex, llm, opts: dict | None = None) -> ArmResult:
    opts = opts or {}
    if arm.startswith("import:"):
        return run_import(arm, root, index, llm, opts)
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r} (choose from {', '.join(ARMS)} or import:<file>)")
    return ARMS[arm](root, index, llm, opts)
