"""Agent population generation (spec STEP 3).

Two sources:
  1. Base archetypes (12 hard-coded types) -> rich personas via LLM.
  2. Product-specific agents generated from the blueprint.

Diversity: archetypes guarantee coverage across motivations by construction.
Archetype agents are generated in parallel via ThreadPoolExecutor; failures
are caught per-agent and warned rather than crashing the whole population.

Latin Hypercube Sampling over the personality vector (spec's orthogonal
coverage) is included as `lhs_personalities` for when you scale to many
variants per archetype; v0 uses one persona per archetype.
"""

from __future__ import annotations

import random
import sys
from concurrent.futures import ThreadPoolExecutor

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


def generate_archetype_agents(blueprint: Blueprint, llm: LLMClient,
                              n: int | None = None) -> list[Agent]:
    archetypes = prompts.ARCHETYPES if n is None else prompts.ARCHETYPES[:n]

    def _one(entry: tuple) -> Agent | None:
        archetype, goal, motivation = entry
        try:
            raw = llm.complete(
                prompts.AGENT_SYSTEM,
                prompts.AGENT_USER.format(
                    archetype=archetype, goal=goal, motivation=motivation,
                    domain=blueprint.domain, name=blueprint.name),
                task="agent",
                max_tokens=llm.scale_tokens(1400),
            )
            return _agent_from_dict(extract_json(raw), archetype)
        except Exception as e:
            print(f"[warn] Agent generation failed for {archetype}: {e}", file=sys.stderr)
            return None

    with ThreadPoolExecutor(max_workers=min(len(archetypes), llm.max_workers)) as pool:
        return [a for a in pool.map(_one, archetypes) if a is not None]


def generate_product_specific_agents(blueprint: Blueprint, llm: LLMClient,
                                     n: int = 3) -> list[Agent]:
    blueprint_block = blueprint.to_prompt_block()

    def _one(i: int) -> Agent | None:
        try:
            raw = llm.complete(
                prompts.PRODUCT_SPECIFIC_AGENTS_SYSTEM,
                prompts.PRODUCT_SPECIFIC_AGENTS_USER.format(
                    n=1, blueprint=blueprint_block),
                task="product_agents",
                max_tokens=llm.scale_tokens(1400),
            )
            data = extract_json(raw)
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                return None
            return _agent_from_dict(data, "PRODUCT-SPECIFIC")
        except Exception as e:
            print(f"[warn] Product-specific agent {i+1} failed: {e}", file=sys.stderr)
            return None

    with ThreadPoolExecutor(max_workers=min(n, llm.max_workers)) as pool:
        return [a for a in pool.map(_one, range(n)) if a is not None]


def build_population(blueprint: Blueprint, llm: LLMClient, *,
                     archetypes: int | None = None,
                     product_specific: int = 3) -> list[Agent]:
    # Both calls are independent — run concurrently.
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_arch = pool.submit(generate_archetype_agents, blueprint, llm, n=archetypes)
        f_ps = (pool.submit(generate_product_specific_agents, blueprint, llm, n=product_specific)
                if product_specific else None)
        pop = f_arch.result()
        if f_ps:
            pop += f_ps.result()
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
