"""Evolutionary simulation (spec STEP 4).

For each generation 1..N:
  - every agent is asked the generation-specific question
  - Gen 1 sees only the product; Gen 2+ see prior findings (the evolution input)
  - findings are deduplicated, scored, and appended with lineage
  - a category coverage block steers agents away from over-represented surfaces

One ThreadPoolExecutor lives for the full simulation; blueprint and prior
are rendered to strings once per generation, not once per agent thread.
"""

from __future__ import annotations

import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from .llm import LLMClient, extract_json
from .models import Agent, Blueprint, Finding
from . import prompts


_ALL_CATS = ["auth", "authz", "rate_limiting", "data_privacy", "billing",
             "injection", "crypto", "config", "supply_chain", "ux"]


def _render_category_coverage(findings: list[Finding]) -> str:
    """Show which attack categories are saturated so agents pick underrepresented ones."""
    if not findings:
        return ""
    cats = Counter(f.attack_category for f in findings if f.attack_category)
    if not cats:
        return ""
    lines = [prompts.CATEGORY_DIVERSITY_HEADER]
    for cat, count in cats.most_common():
        flag = " ← SATURATED, avoid" if count >= 3 else ""
        lines.append(f"  {cat}: {count} finding(s){flag}")
    uncovered = sorted(set(_ALL_CATS) - set(cats.keys()))
    if uncovered:
        lines.append("  uncovered (prioritize): " + ", ".join(uncovered))
    return "\n".join(lines)


def _assign_categories(agents: list, findings: list[Finding]) -> list[str]:
    """Round-robin assign one target category per agent, prioritising uncovered ones.

    Returns a list of category strings, one per agent, in the same order.
    Agents in the same generation get *different* targets so they can't cluster."""
    cats = Counter(f.attack_category for f in findings if f.attack_category)
    # Sort categories: uncovered first (count 0), then least-covered, avoid saturated
    ordered = sorted(_ALL_CATS, key=lambda c: (cats.get(c, 0) >= 3, cats.get(c, 0)))
    assigned = []
    for i, _ in enumerate(agents):
        assigned.append(ordered[i % len(ordered)])
    return assigned


def _render_prior(findings: list[Finding], max_items: int = 12) -> str:
    if not findings:
        return ""
    top = sorted(findings, key=lambda f: f.bss, reverse=True)[:max_items]
    lines = [prompts.PRIOR_FINDINGS_HEADER]
    for f in top:
        lines.append(f"- [{f.title}] (gen {f.generation}, {f.severity_band}): "
                     f"{f.description[:200]}")
    return "\n".join(lines)


def run_agent(agent: Agent, blueprint_block: str, generation: int,
              prior_block: str, category_block: str, target_cat: str,
              llm: LLMClient) -> Finding | None:
    cat_hint = (f"\n----- YOUR ASSIGNED CATEGORY -----\n"
                f"You MUST set attack_category to \"{target_cat}\" for this finding.\n"
                f"Think from this specific attack surface angle only.")
    user = prompts.AGENT_RUN_USER.format(
        persona=agent.to_prompt_block(),
        blueprint=blueprint_block,
        generation=generation,
        instruction=prompts.GENERATION_INSTRUCTIONS[generation],
        prior_block=prior_block,
        category_block=category_block + cat_hint,
    )
    raw = llm.complete(prompts.AGENT_RUN_SYSTEM, user,
                       task=f"finding_gen{generation}", max_tokens=llm.scale_tokens(1200))
    try:
        d = extract_json(raw)
    except Exception as e:
        print(f"[warn] {agent.name} gen{generation}: JSON parse failed ({e})", file=sys.stderr)
        return None
    if not d.get("title"):
        return None
    return Finding(
        title=d["title"].strip(),
        generation=generation,
        discovered_by=agent.name,
        description=d.get("description", ""),
        steps_to_exploit=d.get("steps_to_exploit", []),
        impact=d.get("impact", ""),
        evolved_from=d.get("evolved_from", []),
        attack_category=d.get("attack_category", ""),
        confidence=float(d.get("confidence", 1.0)),
        exploitability=float(d.get("exploitability", 0)),
        impact_score=float(d.get("impact_score", 0)),
        spread=float(d.get("spread", 0)),
        fix_difficulty=float(d.get("fix_difficulty", 1)),
    )


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def _trigrams(s: str) -> set[str]:
    s = _norm(s)
    return {s[i:i + 3] for i in range(len(s) - 2)} if len(s) >= 3 else {s}


def _similar(a: str, b: str, threshold: float = 0.35) -> bool:
    """Trigram Jaccard similarity — catches near-identical titles with different wording."""
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return _norm(a) == _norm(b)
    return len(ta & tb) / len(ta | tb) >= threshold


def _dedup(new: list[Finding], existing: list[Finding]) -> list[Finding]:
    """Drop near-duplicate titles using trigram Jaccard similarity (threshold 0.4)."""
    out: list[Finding] = []
    seen: list[str] = [f.title for f in existing]
    for f in new:
        if not any(_similar(f.title, s) for s in seen):
            seen.append(f.title)
            out.append(f)
    return out


def simulate(blueprint: Blueprint, agents: list[Agent], llm: LLMClient, *,
             generations: int = 3, on_event=None) -> list[Finding]:
    """Run the full evolution. One thread pool is shared across all generations;
    blueprint and prior context are rendered once per generation, not per agent.
    `on_event(kind, payload)` is an optional callback for streaming progress to a UI."""
    if not agents:
        print("[error] No agents were generated — all failed. "
              "This usually means the model is truncating JSON due to token limits. "
              "Try a different model or check your API key.", file=sys.stderr)
        return []
    all_findings: list[Finding] = []
    blueprint_block = blueprint.to_prompt_block()  # computed once total
    with ThreadPoolExecutor(max_workers=min(len(agents), llm.max_workers)) as pool:
        for gen in range(1, generations + 1):
            if on_event:
                on_event("generation_start", {"generation": gen})
            prior_block = _render_prior(all_findings)      # computed once per generation
            category_block = _render_category_coverage(all_findings)
            agent_cats = _assign_categories(agents, all_findings)
            gen_findings: list[Finding] = []
            futures = {
                pool.submit(run_agent, agent, blueprint_block, gen,
                            prior_block, category_block, target_cat, llm): agent
                for agent, target_cat in zip(agents, agent_cats)
            }
            for fut in as_completed(futures):
                f = fut.result()
                if f:
                    gen_findings.append(f)
                    if on_event:
                        on_event("finding", f)
            kept = _dedup(gen_findings, all_findings)
            all_findings.extend(kept)
            if on_event:
                on_event("generation_end",
                         {"generation": gen, "kept": len(kept), "raw": len(gen_findings)})
    return all_findings
