"""Evolutionary simulation (spec STEP 4).

For each generation 1..N:
  - every active agent is asked the generation-specific question
  - Gen 1 sees only the product; Gen 2+ see prior findings (the evolution input)
  - findings are deduplicated, scored, and appended with lineage
  - a category coverage block steers agents away from over-represented surfaces

One ThreadPoolExecutor lives for the full simulation; blueprint and prior
are rendered to strings once per generation, not once per agent thread.
"""

from __future__ import annotations

import sys
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .llm import LLMClient, extract_json
from .models import Agent, Blueprint, Finding
from . import prompts


_ALL_CATS = ["auth", "authz", "rate_limiting", "data_privacy", "billing",
             "injection", "crypto", "config", "supply_chain", "ux",
             "architecture", "code_quality", "error_handling", "scalability"]


POPULATION_DECAY = {
    1: 1.0,
    2: 0.6,
    3: 0.4,
    4: 0.3,
    5: 0.2
}


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


def _render_known_fixed(titles: list[str]) -> str:
    """Render the 'already patched' block that every agent must respect."""
    if not titles:
        return ""
    lines = [prompts.KNOWN_FIXED_HEADER]
    for t in titles:
        lines.append(f"  - {t}")
    return "\n".join(lines)


def _render_inherited_findings(agent: Agent, all_findings: list[Finding]) -> str:
    parent_names = getattr(agent, "parent_names", [])
    if not parent_names:
        return ""
    # Find findings discovered by parents in any previous generations
    parent_findings = [f for f in all_findings if f.discovered_by in parent_names]
    if not parent_findings:
        return ""
    lines = ["\n----- STRATEGY INHERITANCE (vulnerabilities found by your direct predecessors) -----"]
    for f in parent_findings:
        lines.append(f"- [{f.title}] (Severity: {f.severity_band}): {f.description}")
        if f.steps_to_exploit:
            lines.append("  Steps taken: " + " -> ".join(f.steps_to_exploit))
    return "\n".join(lines)


def run_agent(agent: Agent, blueprint_block: str, generation: int,
              prior_block: str, category_block: str, target_cat: str,
              llm: LLMClient, all_findings: list[Finding],
              known_fixed_block: str = "") -> Finding | None:
    cat_hint = (f"\n----- YOUR ASSIGNED CATEGORY -----\n"
                f"You MUST set attack_category to \"{target_cat}\" for this finding.\n"
                f"Think from this specific attack surface angle only.")
    
    # Inject Strategy Inheritance
    parent_strategy_block = _render_inherited_findings(agent, all_findings)
    
    user = prompts.AGENT_RUN_USER.format(
        persona=agent.to_prompt_block(),
        blueprint=blueprint_block,
        generation=generation,
        instruction=prompts.GENERATION_INSTRUCTIONS[generation],
        prior_block=prior_block + parent_strategy_block,
        category_block=category_block + cat_hint,
    )
    # Append the known-fixed block after the formatted template so it
    # doesn't require a template change and is always the last thing the
    # model reads before it writes its answer.
    if known_fixed_block:
        user = user + "\n\n" + known_fixed_block
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


def crossover_parents(P1: Agent, P2: Agent, child_personality: dict[str, float], llm: LLMClient) -> Agent:
    try:
        raw = llm.complete(
            prompts.CROSSOVER_SYSTEM,
            prompts.CROSSOVER_USER.format(
                parent1=P1.to_prompt_block(),
                parent2=P2.to_prompt_block()
            ),
            task="crossover",
            max_tokens=llm.scale_tokens(1000)
        )
        crossover_data = extract_json(raw)
        child = Agent(
            name=crossover_data.get("name", f"Hybrid_{P1.name}_{P2.name}"),
            archetype="HYBRID",
            age=int(crossover_data.get("age", (P1.age + P2.age) // 2)),
            backstory=crossover_data.get("backstory", ""),
            motivation=crossover_data.get("motivation", ""),
            goal=crossover_data.get("goal", ""),
            knowledge=crossover_data.get("knowledge", list(set(P1.knowledge + P2.knowledge))),
            willing_to=crossover_data.get("willing_to", list(set(P1.willing_to + P2.willing_to))),
            unwilling_to=crossover_data.get("unwilling_to", list(set(P1.unwilling_to + P2.unwilling_to))),
            personality=child_personality
        )
        child.parent_names = [P1.name, P2.name]
        return child
    except Exception as e:
        print(f"[warn] Crossover failed: {e}", file=sys.stderr)
        # Fallback to simple merge
        child = Agent(
            name=f"Hybrid_{P1.name}_{P2.name}",
            archetype="HYBRID",
            age=(P1.age + P2.age) // 2,
            backstory=f"A hybrid actor carrying traits from {P1.name} and {P2.name}.",
            motivation=f"Combined motivation: {P1.motivation} & {P2.motivation}",
            goal=f"Combined goal: {P1.goal} & {P2.goal}",
            knowledge=list(set(P1.knowledge + P2.knowledge)),
            willing_to=list(set(P1.willing_to + P2.willing_to)),
            unwilling_to=list(set(P1.unwilling_to + P2.unwilling_to)),
            personality=child_personality
        )
        child.parent_names = [P1.name, P2.name]
        return child


def simulate(blueprint: Blueprint, agents: list[Agent], llm: LLMClient, *,
             generations: int = 3, on_event=None,
             known_fixed: list[str] | None = None) -> list[Finding]:
    """Run the full evolution. One thread pool is shared across all generations;
    blueprint and prior context are rendered once per generation, not per agent.
    `on_event(kind, payload)` is an optional callback for streaming progress to a UI.
    `known_fixed` is an optional list of vulnerability titles that have already
    been patched; agents are explicitly told not to re-report them."""
    known_fixed_block = _render_known_fixed(known_fixed or [])
    if known_fixed_block:
        print(f"[+] Loaded {len(known_fixed)} known-fixed titles — agents will skip these.")
    if not agents:
        print("[error] No agents were generated — all failed.", file=sys.stderr)
        return []
    
    all_findings: list[Finding] = []
    blueprint_block = blueprint.to_prompt_block()  # computed once total
    
    # Store initial population base size
    base_population_size = len(agents)
    active_agents = list(agents)
    
    # Initialize dynamic parent names for Gen 1 agents (none, they have no parents)
    for agent in active_agents:
        if not hasattr(agent, "parent_names"):
            agent.parent_names = []
            
    with ThreadPoolExecutor(max_workers=llm.max_workers) as pool:
        for gen in range(1, generations + 1):
            if gen > 1:
                # 1. Population Scaling
                decay_rate = POPULATION_DECAY.get(gen, 0.2)
                N_g = max(2, round(base_population_size * decay_rate))
                
                # 2. Fitness selection: max BSS score of any finding discovered by the agent in gen-1
                agent_fitness = {}
                for agent in active_agents:
                    # Find findings discovered by this agent in the previous generation
                    prev_gen_findings = [f for f in all_findings if f.discovered_by == agent.name and f.generation == gen - 1]
                    agent_fitness[agent.id] = max([f.bss for f in prev_gen_findings]) if prev_gen_findings else 0.0
                
                # Sort agents based on fitness score
                sorted_agents = sorted(active_agents, key=lambda a: agent_fitness[a.id], reverse=True)
                
                # Select parents (top 50%, minimum of 2 parents)
                parents = sorted_agents[:max(2, len(sorted_agents) // 2)]
                
                # Log selection
                parent_names_str = ", ".join([f"{p.name} (fitness={agent_fitness[p.id]:.2f})" for p in parents])
                msg = f"Gen {gen}: Selected top performing parents: {parent_names_str}"
                print(msg)
                if on_event:
                    on_event("status", {"message": msg})
                
                # 3. Form new active population
                # Keep top parents directly (Elitism)
                elitism_count = min(len(parents), max(1, N_g // 2))
                new_agents = parents[:elitism_count]
                for p in new_agents:
                    p.parent_names = [p.name]  # inherits its own previous strategy
                
                # Perform crossover to fill the rest of the slots
                num_crossovers = N_g - len(new_agents)
                if num_crossovers > 0:
                    crossover_tasks = []
                    for _ in range(num_crossovers):
                        # Pick two parents
                        if len(parents) >= 2:
                            p1, p2 = random.sample(parents, 2)
                        else:
                            p1 = p2 = parents[0]
                        # Combine personality vectors
                        child_personality = {
                            k: round((p1.personality.get(k, 0.5) + p2.personality.get(k, 0.5)) / 2, 2)
                            for k in ["frugality", "tech_savvy", "risk_tolerance", "social_coordination", "patience", "ethics"]
                        }
                        crossover_tasks.append((p1, p2, child_personality))
                    
                    # Run crossover concurrently
                    crossover_futures = [
                        pool.submit(crossover_parents, p1, p2, child_pers, llm)
                        for p1, p2, child_pers in crossover_tasks
                    ]
                    
                    for fut in crossover_futures:
                        child = fut.result()
                        if child:
                            new_agents.append(child)
                            msg = f"Gen {gen}: Created hybrid agent {child.name} from parents {child.parent_names[0]} and {child.parent_names[1]}"
                            print(msg)
                            if on_event:
                                on_event("status", {"message": msg})
                                
                active_agents = new_agents
                msg = f"Gen {gen}: Population scaled down to {len(active_agents)} active agents."
                print(msg)
                if on_event:
                    on_event("status", {"message": msg})
                    
            if on_event:
                on_event("generation_start", {"generation": gen})
                
            prior_block = _render_prior(all_findings)      # computed once per generation
            category_block = _render_category_coverage(all_findings)
            agent_cats = _assign_categories(active_agents, all_findings)
            
            gen_findings: list[Finding] = []
            futures = {
                pool.submit(run_agent, agent, blueprint_block, gen,
                            prior_block, category_block, target_cat, llm,
                            all_findings, known_fixed_block): agent
                for agent, target_cat in zip(active_agents, agent_cats)
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
