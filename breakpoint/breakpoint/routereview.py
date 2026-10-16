"""Review a web app one route at a time, one kind of problem at a time.

A single model shown a whole repository skims it; a model shown one route and told to look for one kind of problem
reads every line it is given. This module takes the route map (routemap.py), and for each route asks only the
questions that route can plausibly raise:

  access control       every route
  untrusted input      routes that read request input and reach eval, a shell, a database query, a file or the response
  redirects / outbound routes that redirect, make an outbound request or touch files
  credentials/session  routes that use the session or handle passwords, and routes whose path looks like login/signup/...
  app-wide setup       once: session cookie flags, signing secret, CSRF, template escaping, security headers

Skipping a (route, question) pair the route's own facts rule out is what keeps the number of model calls small.
Each reviewer sees only that route's code (registration, the protections in front of it, the handler, what it calls)
plus a list of what is active or switched off app-wide. Every finding must cite the exact vulnerable lines; the
citation is checked against the file. The survivors then go through the same source-code verifier as every other
finding, so nothing is reported on a reviewer's word alone.
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import prompts
from .codeindex import CodeIndex
from .coderetrieval import ALL_CATEGORIES, check_refs
from .evolution import _similar
from .llm import LLMClient, LLMFatalError, extract_json
from .models import Finding
from .routemap import Route, RouteMap, map_routes

DEFAULT_CATEGORY = {"authz": "authz", "injection": "injection", "outbound": "injection", "session": "auth", "app": "config"}
_PRIORITY = {"app": 0, "authz": 1, "injection": 1, "outbound": 1, "session": 2}   # what to keep if the call cap bites
_INTERPRETER = {"eval", "shell", "db_query", "file_access", "response_write"}
_OUTBOUND = {"http_request", "redirect", "file_access"}
_SESSIONISH = {"session_use", "credentials"}
_AUTH_PATH = re.compile(r"login|logout|signup|sign-up|register|session|password|passwd|auth|token", re.I)


@dataclass(frozen=True)
class Task:
    focus: str
    route: Route | None = None          # None: the app-wide setup

    @property
    def label(self) -> str:
        return self.route.label if self.route else "app-wide setup"


def applies(focus: str, route: Route) -> bool:
    """Can this route plausibly raise this kind of problem? Decided from what the route map saw, with no model call."""
    sinks = set(route.sinks)
    if focus == "authz":
        return True
    if focus == "injection":
        return route.reads_input and bool(sinks & _INTERPRETER)
    if focus == "outbound":
        return bool(sinks & _OUTBOUND)
    if focus == "session":
        return bool(sinks & _SESSIONISH) or bool(_AUTH_PATH.search(route.path))
    return False


def plan(rm: RouteMap) -> list[Task]:
    tasks = [Task(f, r) for r in rm.routes for f in ("authz", "injection", "outbound", "session") if applies(f, r)]
    if rm.app_level:
        tasks.append(Task("app"))
    return sorted(tasks, key=lambda t: _PRIORITY[t.focus])        # stable: route order is kept inside a priority


# --------------------------------------------------------------------------- what the reviewer is told
def _where(span) -> str:
    return f"{span.file}:{span.start}-{span.end}"


def route_facts(route: Route) -> str:
    mw = []
    for m in route.middleware:
        mw.append(f"{m['name']} (defined at {_where(m['span'])})" if m.get("span")
                  else f"{m['name']} (not defined in this repository: library or dynamic code)")
    h = route.handler.get("span")
    lines = [f"{route.method} {route.path}   (registered at {route.file}:{route.line})",
             "protections in front of it: " + ("; ".join(mw) if mw else "none"),
             f"handler: {route.handler.get('name')}" + (f" at {_where(h)}" if h else " (not found)"),
             f"reads request input: {'yes' if route.reads_input else 'no'}; reaches: {', '.join(route.sinks) or 'nothing notable'}"]
    for v in route.disabled_variants:
        lines.append(f"SWITCHED OFF (a comment, does not run), line {v['line']}: {v['text']}")
    return "\n".join(lines)


def app_facts(rm: RouteMap, limit: int = 24) -> str:
    on = [f"{g['file']}:{g['line']} {g['expr']}" for g in rm.global_middleware if g["active"]][:limit]
    off = [f"{g['file']}:{g['line']} {g['expr']}" for g in rm.global_middleware if not g["active"]][:limit]
    return ("active app-wide middleware: " + ("; ".join(on) or "none seen") + "\n"
            "switched off (commented out, does NOT run): " + ("; ".join(off) or "none seen"))


def app_node_source(rm: RouteMap, index: CodeIndex, max_chars: int) -> str:
    parts, used = [], 0
    for s in rm.app_level:
        if not index.has(s.file) or used >= max_chars:
            continue
        text = index.render_ranges(s.file, [(s.start, s.end)], limit=max(2000, max_chars - used))
        parts.append(text)
        used += len(text)
    return "\n\n".join(parts)


def build_prompt(task: Task, rm: RouteMap, index: CodeIndex, *, max_chars: int, max_findings: int) -> str:
    name, question = prompts.ROUTE_FOCUS[task.focus]
    if task.route is None:
        kind = "THE APP SETUP"
        facts = "entry file: " + (rm.entry_file or "unknown") + "\nconfig files: " + (
            ", ".join(s.file for s in rm.app_level if s.name == "config") or "none")
        code = app_node_source(rm, index, max_chars)
    else:
        kind, facts = "THE ROUTE", route_facts(task.route)
        code = rm.node_source(task.route, index, max_chars)
    return prompts.ROUTE_REVIEW_USER.format(
        focus_name=name, focus_question=question, subject_kind=kind, subject_facts=facts, app_facts=app_facts(rm),
        code_block=code, max_findings=max_findings, categories=" | ".join(ALL_CATEGORIES))


# --------------------------------------------------------------------------- what comes back
def parse_findings(raw: str) -> list[dict]:
    data = extract_json(raw)
    if isinstance(data, dict):
        items = data.get("findings")
        if items is None and data.get("title"):          # extract_json unwraps a one-element array
            items = [data]
    else:
        items = data
    return [d for d in (items if isinstance(items, list) else []) if isinstance(d, dict) and d.get("title")]


def _num(value, default: float, lo: float, hi: float) -> float:
    try:
        return min(max(float(value), lo), hi)
    except (TypeError, ValueError):
        return default


def to_finding(d: dict, task: Task, index: CodeIndex) -> Finding:
    cat = d.get("attack_category")
    steps = d.get("steps_to_exploit", [])
    return Finding(
        title=str(d["title"]).strip(), generation=1,
        discovered_by=f"{prompts.ROUTE_FOCUS[task.focus][0]} reviewer: {task.label}",
        description=str(d.get("description", "")),
        steps_to_exploit=[str(s) for s in steps] if isinstance(steps, list) else [str(steps)],
        impact=str(d.get("impact", "")),
        attack_category=cat if cat in ALL_CATEGORIES else DEFAULT_CATEGORY[task.focus],
        exploitability=_num(d.get("exploitability"), 0, 0, 10), impact_score=_num(d.get("impact_score"), 0, 0, 10),
        spread=_num(d.get("spread"), 0, 0, 10), fix_difficulty=_num(d.get("fix_difficulty"), 1, 1, 10),
        code_refs=check_refs(index, d.get("code_refs")))


def _same(a: Finding, b: Finding) -> bool:
    if _similar(a.title, b.title, 0.5):
        return True
    near = any(x["file"] == y["file"] and abs(x["line"] - y["line"]) <= 1 for x in a.code_refs for y in b.code_refs)
    return near and a.attack_category == b.attack_category


def merge_duplicates(findings: list[Finding]) -> list[Finding]:
    """One finding per problem: the same bug seen by several reviewers (or on several routes) is kept once, with every
    place it was seen listed in `discovered_by`. The copy with more verified citations (then higher score) is kept."""
    out: list[Finding] = []
    for f in findings:
        i = next((k for k, g in enumerate(out) if _same(f, g)), None)
        if i is None:
            out.append(f)
            continue
        twin = out[i]
        keep, drop = (f, twin) if (len(f.code_refs), f.bss) > (len(twin.code_refs), twin.bss) else (twin, f)
        seen = [s.strip() for s in (keep.discovered_by + ";" + drop.discovered_by).split(";") if s.strip()]
        keep.discovered_by = "; ".join(dict.fromkeys(seen))
        out[i] = keep
    return out


# --------------------------------------------------------------------------- running it
@dataclass
class ReviewResult:
    findings: list[Finding] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    candidates: int = 0                 # before merging duplicates
    errors: list[str] = field(default_factory=list)
    skipped_by_cap: int = 0


def _say(*args) -> None:
    print(*args, flush=True)          # progress must show up while a long run is redirected to a file


def review(index: CodeIndex, llm, rm: RouteMap, *, max_calls: int = 150, max_findings: int = 3,
           max_chars: int = 14000, log=_say) -> ReviewResult:
    tasks = plan(rm)
    result = ReviewResult(skipped_by_cap=max(0, len(tasks) - max_calls))
    result.tasks = tasks[:max_calls]
    if result.skipped_by_cap:
        log(f"[warn] {len(tasks)} reviews planned, running the first {max_calls} (--review-max-calls); "
            f"{result.skipped_by_cap} lower-priority ones are skipped.")

    def run(task: Task):
        try:
            prompt = build_prompt(task, rm, index, max_chars=max_chars, max_findings=max_findings)
            raw = llm.complete(prompts.ROUTE_REVIEW_SYSTEM, prompt, task="route_review", max_tokens=llm.scale_tokens(3000))
            return task, [to_finding(d, task, index) for d in parse_findings(raw)[:max_findings]], None
        except LLMFatalError:
            raise
        except Exception as e:                                           # one bad reply must not lose the other reviews
            return task, [], f"{task.focus} {task.label}: {type(e).__name__}: {str(e)[:160]}"

    workers = max(1, min(getattr(llm, "max_workers", 1), len(result.tasks) or 1))
    collected: list[Finding] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for n, (task, found, err) in enumerate(pool.map(run, result.tasks), 1):
            if err:
                result.errors.append(err)
            collected += found
            log(f"[{n}/{len(result.tasks)}] {task.focus:<9} {task.label}: " + (f"error" if err else f"{len(found)} candidate(s)"))
    result.candidates = len(collected)
    result.findings = merge_duplicates(collected)
    return result


def _save(out_path: str, data: dict) -> None:
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError as e:
        sys.exit(f"Cannot write {out_path!r}: {e}")


def run_route_review(codebase: str, out_path: str, *, verify: bool = True, max_calls: int = 150, llm=None,
                     verifier_factory=None) -> dict:
    from .blueprint import codebase_checkout
    from .codeverify import CodeVerifier
    llm = llm or LLMClient()
    print(f"Provider: {llm.provider} | Model: {llm.model}")
    with codebase_checkout(codebase) as root:
        index = CodeIndex.from_dir(root)
        rm = map_routes(index)
        if rm.framework is None:
            sys.exit("Route review reads Express apps only and found none here. Use the standard scan "
                     "(python -m breakpoint.run --codebase ...) for other frameworks.")
        print(f"{len(index)} files, {len(rm.routes)} routes; planning reviews...")
        result = review(index, llm, rm, max_calls=max_calls)
        print(f"{len(result.tasks)} reviews -> {result.candidates} candidate findings -> {len(result.findings)} after merging duplicates"
              + (f" ({len(result.errors)} reviews failed)" if result.errors else ""))
        meta = {"model": f"{llm.provider}/{llm.model}", "routes": len(rm.routes), "reviews": len(result.tasks),
                "candidates": result.candidates, "after_merging": len(result.findings),
                "skipped_by_cap": result.skipped_by_cap, "errors": result.errors}

        def report(kept, stats, checked, stage):
            return {"route_review": {**meta, "checked_against_code": checked, "stage": stage},
                    "findings": [f.to_dict() for f in kept], "verification": stats}

        # Save what the reviewers found before spending more calls: a provider failure while checking must not lose it.
        _save(out_path, report(result.findings, None, False, "candidates, not yet checked against the code"))
        kept, stats = result.findings, None
        if verify and result.findings:
            print(f"Checking {len(result.findings)} candidates against the real code...")
            verifier = (verifier_factory or CodeVerifier)(index, llm)
            try:
                outcome = verifier(result.findings)
            except LLMFatalError:
                print(f"[!] The reviews are saved in {out_path} (unchecked). Check them later with: "
                      f"python -m breakpoint.run --verify-report {out_path} --codebase {codebase} --output checked.json")
                raise
            kept = []
            for f, r in zip(result.findings, outcome):
                if r["status"] == "CONFIRMED":
                    f.verification, f.evidence = "CONFIRMED", r["evidence_items"]
                    kept.append(f)
            stats = verifier.stats()
            print(f"{stats['confirmed']} of {stats['checked']} held up ({stats['refuted']} refuted, "
                  f"{stats['unverified']} unproven, {stats['errors']} errors).")
    data = report(kept, stats, bool(verify), "done")
    _save(out_path, data)
    print(f"[+] Saved {len(kept)} findings to {out_path}" + ("" if verify else " (NOT checked against the code: they may be wrong)"))
    for f in kept:
        cites = ", ".join(f"{e['file']}:{e['line']}" for e in (f.evidence or f.code_refs)[:3])
        print(f"  [{f.severity_band}] {f.title}" + (f"   ({cites})" if cites else ""))
    return data
