"""Head-to-head: Breakpoint's engine vs one plain prompt, both judged by the referee.

Both arms produce *claimed* vulnerabilities in the same shape. Each claim is turned
into an exploit script by the same translator prompt, run against NoteShare, and
judged by the spec. The translator never sees which flaws exist.

  python -m breakpoint.bench.harness --agents 8 --gens 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..agents import build_population
from ..evolution import simulate
from ..llm import LLMClient, extract_json
from ..models import Blueprint, Flow
from .noteshare import FLAWS
from .spec import CLAIMS, FLAW_OF_CLAIM
from .verify import CONFIRMED, INVALID, NOT_REPRODUCED, run_script

UNTESTABLE, OFF_TARGET = "UNTESTABLE", "OFF_TARGET"

NOTESHARE_BLUEPRINT = Blueprint(
    name="NoteShare", type="SaaS web app (JSON API)", domain="Team notes", stage="Live",
    actors=["alice: member of org A, free plan", "bob: member of org A, free plan",
            "carol: member of org B, pro plan", "root: admin of org A, pro plan",
            "Anonymous visitor: can only open public share links"],
    resources=["Notes (owner, title, body)", "Per-note share list", "Per-note public share link"],
    boundaries=["Orgs are separate tenants; sharing stays inside the owner's org",
                "Only a note's owner can change, share, unshare or link it"],
    flows=[Flow("Write and share", ["create note", "share with a teammate", "teammate reads it"]),
           Flow("Public link", ["owner makes a link", "anyone with the link reads the note",
                                "owner revokes sharing"]),
           Flow("Migrate", ["bulk import notes from another tool"])],
    mechanical_details=[
        "POST /notes {title, body}: create a note. Free plan: at most 5 live notes (402 when exceeded).",
        "POST /notes/import {notes:[{title, body}]}: bulk-create notes.",
        "GET /notes/{id}: read a note. Allowed for the owner, users it is shared with, and admins.",
        "PUT /notes/{id} {body} and DELETE /notes/{id}: owner only.",
        "POST /notes/{id}/share {user}: owner only. The recipient must be in the owner's org.",
        "POST /notes/{id}/unshare_all: owner only. Revokes all sharing, including the public link.",
        "POST /notes/{id}/link: owner only. Returns {token}. GET /s/{token} reads the note with no login.",
        "GET /admin/notes/{id}: admins only.",
    ],
    known_unknowns=[],
    attack_surface=["POST /notes", "POST /notes/import", "GET /notes/{id}", "PUT /notes/{id}",
                    "DELETE /notes/{id}", "POST /notes/{id}/share", "POST /notes/{id}/unshare_all",
                    "POST /notes/{id}/link", "GET /s/{token}", "GET /admin/notes/{id}"],
)

API_REFERENCE = """\
USERS (log in by name): alice (org A, free), bob (org A, free), carol (org B, pro), root (org A, admin).
Use "as": null for an anonymous request.
STARTING NOTES: id 1 owned by alice, id 2 by bob, id 3 by carol. New notes get the next id.
ROUTES AND RESPONSES:
  POST /notes {"title","body"}                 -> 201 {"ids":[..],"id":n}   (402 over the free limit)
  POST /notes/import {"notes":[{"title"}..]}   -> 201 {"ids":[..],"id":n}
  GET /notes/{id}                              -> 200 note | 403 | 404
  PUT /notes/{id} {"body"}                     -> 200 note | 403
  DELETE /notes/{id}                           -> 200 | 403
  POST /notes/{id}/share {"user"}              -> 200 {"shared_with":[..]} | 403 | 404
  POST /notes/{id}/unshare_all                 -> 200
  POST /notes/{id}/link                        -> 200 {"token"}
  GET /s/{token}                               -> 200 note | 404   (no login)
  GET /admin/notes/{id}                        -> 200 note | 403
SCRIPT FORMAT: a JSON list of steps. Each step: {"as": "bob" or null, "method": "GET|POST|PUT|DELETE",
  "path": "/notes/1", "body": {..optional..}, "save": {"var": "responseField"} optional}.
  "save" copies a top-level response field into a variable; use it later as {var} in a path or body.
  Example: [{"as":"alice","method":"POST","path":"/notes/1/link","save":{"tok":"token"}},
            {"as":null,"method":"GET","path":"/s/{tok}"}]
"""

TRANSLATE_SYSTEM = (
    "You turn a claimed vulnerability into a short test script for a small JSON API. "
    "Write exactly what the claim describes and nothing more. You do not decide whether the claim "
    "is true; the script will be run and the app's real behaviour decides. Output only JSON."
)

TRANSLATE_USER = """{api}
CLAIM
Title: {title}
Description: {description}
Steps: {steps}

RULES (the product's stated policies):
{rules}

Return {{"script": [...], "rule": "<RULE NAME>"}} in the script format above (at most 12 steps, only
routes listed above). "rule" is the ONE rule above that this claim says is broken, or "NONE" if the claim
is not about any of them. Keep the script to what the claim needs; do not add extra probing.
Return {{"script": null}} if the claim cannot be tested with this API (it needs network sniffing,
source code, brute-forcing secrets, or a feature that does not exist).
"""

BASELINE_SYSTEM = "You are a careful application security reviewer. Output only JSON."

BASELINE_USER = """Review this product for security and business-logic vulnerabilities.

{blueprint}

List exactly {k} distinct vulnerabilities, most serious first. Return a JSON array where each item is
{{"title": "...", "description": "...", "steps_to_exploit": ["...", "..."]}}.
"""


RULES_TEXT = "\n".join(f"  {name}: {text}" for name, text in CLAIMS.items())


class CountingLLM(LLMClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0
        self._lock = threading.Lock()

    @property
    def max_workers(self) -> int:
        return min(super().max_workers, 2)  # three parallel callers exceeded OpenAI's 30k tokens/min

    def complete(self, *args, **kwargs):
        with self._lock:
            self.calls += 1  # a logical call; the retries below are not counted again
        for attempt in range(8):
            try:
                return super().complete(*args, **kwargs)
            except RuntimeError as e:
                if "HTTP 429" not in str(e) or attempt == 7:
                    raise
                time.sleep(5 + 5 * attempt)


def evaluate(claims: list[dict], llm) -> list[dict]:
    """Translate each claim to an exploit script, run it, and attach the referee's verdict."""
    def one(c: dict) -> dict:
        try:
            raw = llm.complete(
                TRANSLATE_SYSTEM,
                TRANSLATE_USER.format(api=API_REFERENCE, rules=RULES_TEXT, title=c["title"], description=c["description"],
                                      steps=" | ".join(map(str, c.get("steps", [])))),
                task="translate", max_tokens=1500)
            reply = extract_json(raw)
            script, rule = reply["script"], str(reply.get("rule", "NONE"))
        except Exception as e:  # noqa: BLE001 - a bad model reply is one untestable claim, not a crashed run
            return {**c, "status": UNTESTABLE, "error": f"{type(e).__name__}: {e}"[:200]}
        if script is None:
            return {**c, "status": UNTESTABLE, "error": "translator said it cannot be tested"}
        r = run_script(script)
        broken = sorted({v.claim for v in r.violations})
        status = r.status
        if status == CONFIRMED and rule not in broken:
            status = OFF_TARGET  # the script broke some other rule; no credit for what the claim never said
        flaws = [FLAW_OF_CLAIM[rule]] if status == CONFIRMED and rule in FLAW_OF_CLAIM else []
        trace = [f"{e['actor'] or 'anonymous'} {e['method']} {e['path']} -> {e['status']}" for e in r.log]
        return {**c, "script": script, "rule": rule, "status": status, "claims_broken": broken,
                "flaws": flaws, "error": r.error, "trace": trace}

    with ThreadPoolExecutor(max_workers=llm.max_workers) as pool:
        return list(pool.map(one, claims))


def summarize(rows: list[dict]) -> dict:
    tested = [r for r in rows if r["status"] in (CONFIRMED, NOT_REPRODUCED, OFF_TARGET)]
    real = [r for r in rows if r["status"] == CONFIRMED]
    by_gen: dict[int, dict] = defaultdict(lambda: {"claims": 0, "tested": 0, "real": 0})
    for r in rows:
        g = by_gen[r.get("generation", 0)]
        g["claims"] += 1
        g["tested"] += r["status"] in (CONFIRMED, NOT_REPRODUCED, OFF_TARGET)
        g["real"] += r["status"] == CONFIRMED
    return {
        "claims": len(rows),
        "untestable": sum(r["status"] == UNTESTABLE for r in rows),
        "tested": len(tested),
        "real": len(real),
        "not_real": sum(r["status"] == NOT_REPRODUCED for r in rows),
        "off_target": sum(r["status"] == OFF_TARGET for r in rows),
        "invalid": sum(r["status"] == INVALID for r in rows),
        "real_share_of_tested": round(len(real) / len(tested), 2) if tested else None,
        "planted_found": sorted({f for r in real for f in r["flaws"]}),
        "planted_total": len(FLAWS),
        "by_generation": {g: dict(v) for g, v in sorted(by_gen.items())},
    }


def _claims_from(findings) -> list[dict]:
    return [{"title": f.title, "description": f.description, "steps": f.steps_to_exploit,
             "generation": f.generation, "by": f.discovered_by} for f in findings]


def _evidence(row: dict) -> str:
    """What to tell the next generation about a claim that did not hold."""
    if row["status"] in (UNTESTABLE, INVALID):
        return "could not be run as API requests, so it proves nothing."
    seen = "; ".join(row.get("trace", [])[:8]) or "no requests"
    if row["status"] == OFF_TARGET:
        return f"ran, but did not break the rule it claimed. Observed: {seen}."
    return f"ran, and the app behaved correctly. Observed: {seen}."


def run_engine_arm(llm, agents: int, gens: int, verified: bool = False) -> list[dict]:
    pop = build_population(NOTESHARE_BLUEPRINT, llm, total_agents=agents)
    if not verified:
        return evaluate(_claims_from(simulate(NOTESHARE_BLUEPRINT, pop, llm, generations=gens)), llm)

    rows: list[dict] = []

    def verifier(findings):
        results = evaluate(_claims_from(findings), llm)
        rows.extend(results)
        return [{"ok": r["status"] == CONFIRMED, "evidence": _evidence(r)} for r in results]

    simulate(NOTESHARE_BLUEPRINT, pop, llm, generations=gens, verifier=verifier)
    return rows


def run_baseline_arm(llm, k: int) -> list[dict]:
    raw = llm.complete(BASELINE_SYSTEM,
                       BASELINE_USER.format(blueprint=NOTESHARE_BLUEPRINT.to_prompt_block(), k=k),
                       task="baseline", max_tokens=llm.scale_tokens(4000))
    items = extract_json(raw)
    claims = [{"title": str(i.get("title", "")), "description": str(i.get("description", "")),
               "steps": i.get("steps_to_exploit", []), "generation": 1, "by": "single prompt"}
              for i in items if isinstance(i, dict)][:k]
    return evaluate(claims, llm)


ARM_NAMES = {"engine": "BREAKPOINT today (nothing checked inside the loop)",
             "verified": "BREAKPOINT with the referee inside the loop",
             "single": "SINGLE PROMPT (one question to the same model)"}


def _describe(name: str, calls: int, s: dict) -> str:
    share = "n/a" if s["real_share_of_tested"] is None else f"{round(s['real_share_of_tested'] * 100)}%"
    lines = [f"{name}  ({calls} model calls)",
             f"  claimed bugs: {s['claims']} | could be tested: {s['tested']} | actually real: {s['real']} | "
             f"not real: {s['not_real']} | wrong rule: {s['off_target']} | broken scripts: {s['invalid']} | "
             f"untestable: {s['untestable']}",
             f"  share of tested claims that were real: {share}",
             f"  planted bugs found: {len(s['planted_found'])} of {s['planted_total']} {s['planted_found']}"]
    if len(s["by_generation"]) > 1:
        lines.append("  by generation: " + "; ".join(
            f"gen {g}: {v['real']} real of {v['tested']} tested" for g, v in s["by_generation"].items()))
    return "\n".join(lines)


def _averages(runs: list[dict], arm: str) -> str:
    sums = [r[arm]["summary"] for r in runs if arm in r]
    shares = [s["real_share_of_tested"] for s in sums if s["real_share_of_tested"] is not None]
    avg = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
    return (f"  {ARM_NAMES[arm]}\n"
            f"      real share of tested claims: {round(avg(shares) * 100)}% | "
            f"planted bugs found: {avg([len(s['planted_found']) for s in sums]):.1f} of {sums[0]['planted_total']} | "
            f"model calls: {avg([r[arm]['calls'] for r in runs if arm in r]):.0f}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Breakpoint engine vs single prompt on the NoteShare benchmark")
    p.add_argument("--agents", type=int, default=8)
    p.add_argument("--gens", type=int, default=3)
    p.add_argument("--repeat", type=int, default=1, help="repeat everything N times; one run is mostly luck")
    p.add_argument("--arms", default="engine,verified,single", help="comma list of: engine, verified, single")
    p.add_argument("--out", default="bench_runs")
    args = p.parse_args(argv)
    arms = [a for a in args.arms.split(",") if a in ARM_NAMES]

    llm = CountingLLM()
    key = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}.get(llm.provider)
    if not key or not os.getenv(key):
        sys.exit(f"No API key for provider {llm.provider!r}. Set BREAKPOINT_PROVIDER and its key first.")
    print(f"Provider: {llm.provider} | Model: {llm.model}\n")

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    path = out / f"run_{time.strftime('%Y%m%d_%H%M%S')}.json"
    runs: list[dict] = []
    for i in range(args.repeat):
        print(f"\n######## repeat {i + 1} of {args.repeat} ########")
        run: dict = {}
        k = 15
        for arm in arms:
            before = llm.calls
            if arm == "single":
                rows = run_baseline_arm(llm, k)
            else:
                rows = run_engine_arm(llm, args.agents, args.gens, verified=(arm == "verified"))
                if arm == "engine":
                    k = min(max(len(rows), 5), 25)
            run[arm] = {"calls": llm.calls - before, "summary": summarize(rows), "rows": rows}
        runs.append(run)
        path.write_text(json.dumps({"provider": llm.provider, "model": llm.model, "agents": args.agents,
                                    "gens": args.gens, "runs": runs}, indent=2), encoding="utf-8")
        print("\n" + "=" * 70)
        for arm in arms:
            print(_describe(ARM_NAMES[arm], run[arm]["calls"], run[arm]["summary"]) + "\n")
        print("=" * 70)

    if args.repeat > 1:
        print(f"\nAVERAGE OVER {args.repeat} RUNS")
        for arm in arms:
            print(_averages(runs, arm))

    print(f"\nFull details saved to {path}")


if __name__ == "__main__":
    main()
