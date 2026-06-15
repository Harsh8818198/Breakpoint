"""Agent population generation (spec STEP 3).

Two sources:
  1. Base archetypes (12 hard-coded types) -> rich personas via LLM.
  2. Product-specific agents generated from the blueprint.
  3. Custom agents defined by user scenarios.

Diversity: archetypes guarantee coverage across motivations by construction.
Archetype agents are generated in parallel via ThreadPoolExecutor; failures
are caught per-agent and warned rather than crashing the whole population.

Latin Hypercube Sampling over the personality vector (spec's orthogonal
coverage) is included as `lhs_personalities` to scale and modulate agents' traits.
"""

from __future__ import annotations

import random
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .llm import LLMClient, extract_json
from .models import Agent, Blueprint
from . import prompts


def _agent_from_dict(d: dict, archetype: str) -> Agent:
    return Agent(
        name=d.get("name", "Unnamed"),
        archetype=d.get("archetype", archetype),
        age=int(d.get("age", 25)),
        backstory=d.get("backstory", ""),
        motivation=d.get("motivation", ""),
        goal=d.get("goal", ""),
        knowledge=d.get("knowledge", []),
        willing_to=d.get("willing_to", []),
        unwilling_to=d.get("unwilling_to", []),
        personality=d.get("personality", {}),
    )


def get_archetype_info(key: str) -> tuple[str, str, str]:
    k = key.lower().strip()
    if "freeload" in k:
        return ("THE FREELOADER", "never pay", "cost")
    if "guardian" in k or "privacy" in k:
        return ("THE GUARDIAN", "protect privacy", "safety")
    if "power" in k:
        return ("THE POWER USER", "maximize efficiency", "output")
    if "chaos" in k or "griefer" in k or "hacker" in k:
        return ("THE GRIEFER", "ruin others' experience", "chaos")
    if "social" in k or "organizer" in k:
        return ("THE ORGANIZER", "coordinate groups", "social")
    if "naive" in k:
        return ("THE NAIVE USER", "just use the product", "task completion")
    if "critic" in k:
        return ("THE CRITIC", "find UX failures", "frustration")
    if "competitor" in k:
        return ("THE COMPETITOR", "extract intelligence", "business")
    if "regulator" in k:
        return ("THE REGULATOR", "find compliance issues", "legal")
    if "scalper" in k:
        return ("THE SCALPER", "exploit for profit", "money")
    if "advocate" in k:
        return ("THE ADVOCATE", "warn others", "community")
    
    # Fallback to look up in prompts.ARCHETYPES
    for arch, goal, mot in prompts.ARCHETYPES:
        if k in arch.lower():
            return arch, goal, mot
            
    # Default fallback
    return ("THE NAIVE USER", "just use the product", "task completion")


def generate_one_archetype_agent(blueprint: Blueprint, llm: LLMClient, archetype: str, goal: str, motivation: str, personality_vector: list[float]) -> Agent | None:
    try:
        user_prompt = prompts.AGENT_USER.format(
            archetype=archetype, goal=goal, motivation=motivation,
            domain=blueprint.domain, name=blueprint.name
        )
        # Append LHS personality traits to the prompt
        user_prompt += (
            f"\n\nYou MUST generate this agent such that their personality traits align with: "
            f"frugality={personality_vector[0]:.2f}, tech_savvy={personality_vector[1]:.2f}, "
            f"risk_tolerance={personality_vector[2]:.2f}, social_coordination={personality_vector[3]:.2f}, "
            f"patience={personality_vector[4]:.2f}, ethics={personality_vector[5]:.2f}."
        )
        raw = llm.complete(
            prompts.AGENT_SYSTEM,
            user_prompt,
            task="agent",
            max_tokens=llm.scale_tokens(1400),
        )
        agent_data = extract_json(raw)
        if "personality" not in agent_data:
            agent_data["personality"] = {
                "frugality": personality_vector[0],
                "tech_savvy": personality_vector[1],
                "risk_tolerance": personality_vector[2],
                "social_coordination": personality_vector[3],
                "patience": personality_vector[4],
                "ethics": personality_vector[5]
            }
        return _agent_from_dict(agent_data, archetype)
    except Exception as e:
        print(f"[warn] Agent generation failed for {archetype}: {e}", file=sys.stderr)
        return None


def generate_custom_agent(blueprint: Blueprint, llm: LLMClient, spec: str | dict[str, Any], personality_vector: list[float] | None = None) -> Agent | None:
    if isinstance(spec, dict) and all(k in spec for k in ["name", "backstory", "goal", "motivation"]):
        # It's already a complete agent persona dict
        return _agent_from_dict(spec, spec.get("archetype", "CUSTOM"))
    
    # Otherwise, it's a scenario description we need the LLM to flesh out
    scenario = spec if isinstance(spec, str) else spec.get("description", spec.get("scenario", str(spec)))
    try:
        user_prompt = prompts.CUSTOM_AGENT_USER.format(
            scenario=scenario,
            domain=blueprint.domain,
            name=blueprint.name
        )
        if personality_vector:
            user_prompt += (
                f"\n\nYou MUST generate this agent such that their personality traits align with: "
                f"frugality={personality_vector[0]:.2f}, tech_savvy={personality_vector[1]:.2f}, "
                f"risk_tolerance={personality_vector[2]:.2f}, social_coordination={personality_vector[3]:.2f}, "
                f"patience={personality_vector[4]:.2f}, ethics={personality_vector[5]:.2f}."
            )
        raw = llm.complete(
            prompts.CUSTOM_AGENT_SYSTEM,
            user_prompt,
            task="custom_agent",
            max_tokens=llm.scale_tokens(1400)
        )
        agent_data = extract_json(raw)
        if personality_vector and "personality" not in agent_data:
            agent_data["personality"] = {
                "frugality": personality_vector[0],
                "tech_savvy": personality_vector[1],
                "risk_tolerance": personality_vector[2],
                "social_coordination": personality_vector[3],
                "patience": personality_vector[4],
                "ethics": personality_vector[5]
            }
        return _agent_from_dict(agent_data, "CUSTOM")
    except Exception as e:
        print(f"[warn] Custom agent generation failed: {e}", file=sys.stderr)
        return None


def generate_product_specific_agents(blueprint: Blueprint, llm: LLMClient,
                                     n: int = 3, personality_vectors: list[list[float]] | None = None) -> list[Agent]:
    blueprint_block = blueprint.to_prompt_block()

    def _one(idx: int) -> Agent | None:
        p_vec = personality_vectors[idx] if personality_vectors and idx < len(personality_vectors) else None
        try:
            user_prompt = prompts.PRODUCT_SPECIFIC_AGENTS_USER.format(
                n=1, blueprint=blueprint_block)
            if p_vec:
                user_prompt += (
                    f"\n\nYou MUST generate this agent such that their personality traits align with: "
                    f"frugality={p_vec[0]:.2f}, tech_savvy={p_vec[1]:.2f}, "
                    f"risk_tolerance={p_vec[2]:.2f}, social_coordination={p_vec[3]:.2f}, "
                    f"patience={p_vec[4]:.2f}, ethics={p_vec[5]:.2f}."
                )
            raw = llm.complete(
                prompts.PRODUCT_SPECIFIC_AGENTS_SYSTEM,
                user_prompt,
                task="product_agents",
                max_tokens=llm.scale_tokens(1400),
            )
            data = extract_json(raw)
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                return None
            if p_vec and "personality" not in data:
                data["personality"] = {
                    "frugality": p_vec[0],
                    "tech_savvy": p_vec[1],
                    "risk_tolerance": p_vec[2],
                    "social_coordination": p_vec[3],
                    "patience": p_vec[4],
                    "ethics": p_vec[5]
                }
            return _agent_from_dict(data, "PRODUCT-SPECIFIC")
        except Exception as e:
            print(f"[warn] Product-specific agent {idx+1} failed: {e}", file=sys.stderr)
            return None

    with ThreadPoolExecutor(max_workers=min(n, llm.max_workers)) as pool:
        return [a for a in pool.map(_one, range(n)) if a is not None]


def build_population(blueprint: Blueprint, llm: LLMClient, *,
                     total_agents: int = 10,
                     agent_composition: dict[str, float] = None,
                     custom_agents: list[dict[str, Any]] = None,
                     focus_areas: list[str] = None) -> list[Agent]:
    custom_agents_list = custom_agents or []
    num_custom = len(custom_agents_list)
    
    if agent_composition:
        # Filter composition to non-zero values
        filtered_comp = {k: v for k, v in agent_composition.items() if v > 0}
        if not filtered_comp:
            # Fallback to default equal distribution of core archetypes
            filtered_comp = {
                "Freeloaders": 1.0,
                "Privacy Guardians": 1.0,
                "Power Users": 1.0,
                "Chaos Agents": 1.0,
                "Social Engineers": 1.0,
                "Naive Users": 1.0
            }
        num_ps = 0
    else:
        # If no composition, default to core archetypes + 2 product specific agents
        filtered_comp = {
            "Freeloaders": 1.0,
            "Privacy Guardians": 1.0,
            "Power Users": 1.0,
            "Chaos Agents": 1.0,
            "Social Engineers": 1.0,
            "Naive Users": 1.0
        }
        num_ps = min(2, max(0, total_agents - num_custom))
        
    num_arch = max(0, total_agents - num_custom - num_ps)
    
    # Proportional allocation of archetype slots
    arch_keys = list(filtered_comp.keys())
    weights = [filtered_comp[k] for k in arch_keys]
    total_weight = sum(weights)
    
    arch_infos = [get_archetype_info(k) for k in arch_keys]
    
    allocated = 0
    temp_counts = []
    for arch_info, w in zip(arch_infos, weights):
        share = (w / total_weight) * num_arch if total_weight > 0 else 0
        count = int(share)
        allocated += count
        remainder = share - count
        temp_counts.append([arch_info, count, remainder])
        
    if num_arch > 0:
        temp_counts.sort(key=lambda x: x[2], reverse=True)
        i = 0
        while allocated < num_arch:
            temp_counts[i % len(temp_counts)][1] += 1
            allocated += 1
            i += 1
            
    # Compile the list of archetype tasks to run
    archetype_tasks = []
    for arch_info, count, _ in temp_counts:
        for _ in range(count):
            archetype_tasks.append(arch_info)
            
    # We generate a total of num_custom + num_ps + len(archetype_tasks) agents.
    actual_count = num_custom + num_ps + len(archetype_tasks)
    if actual_count == 0:
        return []
        
    # Generate Latin Hypercube personality vectors
    p_vectors = lhs_personalities(actual_count, dims=6)
    
    # We will run all generation tasks concurrently
    pop: list[Agent] = []
    
    # We want to match each agent generated to its unique LHS personality vector
    vec_idx = 0
    
    # 1. Custom agents
    custom_futures = []
    with ThreadPoolExecutor(max_workers=min(max(1, num_custom), llm.max_workers)) as pool:
        for spec in custom_agents_list:
            p_vec = p_vectors[vec_idx]
            vec_idx += 1
            custom_futures.append(pool.submit(generate_custom_agent, blueprint, llm, spec, p_vec))
        for fut in custom_futures:
            agent = fut.result()
            if agent:
                pop.append(agent)
                
    # 2. Product-specific agents
    if num_ps > 0:
        ps_vectors = p_vectors[vec_idx:vec_idx + num_ps]
        vec_idx += num_ps
        ps_agents = generate_product_specific_agents(blueprint, llm, n=num_ps, personality_vectors=ps_vectors)
        pop.extend(ps_agents)
        
    # 3. Archetype agents
    arch_futures = []
    with ThreadPoolExecutor(max_workers=min(max(1, len(archetype_tasks)), llm.max_workers)) as pool:
        for arch, goal, mot in archetype_tasks:
            p_vec = p_vectors[vec_idx]
            vec_idx += 1
            arch_futures.append(pool.submit(generate_one_archetype_agent, blueprint, llm, arch, goal, mot, p_vec))
        for fut in arch_futures:
            agent = fut.result()
            if agent:
                pop.append(agent)
                
    return pop


def lhs_personalities(n: int, dims: int = 6, seed: int = 0) -> list[list[float]]:
    """Latin Hypercube Sampling: n points spread evenly across `dims` axes so
    no two agents cluster (spec's 'orthogonal coverage'). For scaling to many
    variants per archetype later."""
    rng = random.Random(seed)
    cols = []
    for _ in range(dims):
        bins = [(i + rng.random()) / n for i in range(n)]
        rng.shuffle(bins)
        cols.append(bins)
    return [[cols[d][i] for d in range(dims)] for i in range(n)]
