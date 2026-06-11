"""Product intake -> Blueprint (spec STEP 1).

v0 implements Mode 1 in its non-interactive form: raw description -> blueprint.
The interactive interrogation + verification loop (follow-up questions, read-back,
refinement cycles) is stubbed in `interrogate()` for the next phase.
"""

from __future__ import annotations

import sys

from .llm import LLMClient, extract_json
from .models import Blueprint, Flow
from . import prompts

_REQUIRED_FIELDS = ("name", "domain", "actors", "attack_surface", "known_unknowns")


def build_blueprint(description: str, llm: LLMClient) -> Blueprint:
    raw = llm.complete(
        prompts.BLUEPRINT_SYSTEM,
        prompts.BLUEPRINT_USER.format(description=description),
        task="blueprint",
        max_tokens=llm.scale_tokens(6000),
    )
    data = extract_json(raw)

    for field in _REQUIRED_FIELDS:
        if not data.get(field):
            print(f"[warn] Blueprint field {field!r} is empty — finding quality will suffer",
                  file=sys.stderr)

    flows = [Flow(name=f.get("name", ""), steps=f.get("steps", []))
             for f in data.get("flows", [])]
    return Blueprint(
        name=data.get("name") or "Unknown product",
        type=data.get("type", ""),
        domain=data.get("domain", ""),
        stage=data.get("stage", ""),
        actors=data.get("actors", []),
        resources=data.get("resources", []),
        boundaries=data.get("boundaries", []),
        flows=flows,
        mechanical_details=data.get("mechanical_details", []),
        known_unknowns=data.get("known_unknowns", []),
        attack_surface=data.get("attack_surface", []),
    )


def interrogate(blueprint: Blueprint, llm: LLMClient) -> list[str]:
    """Phase 2 (next milestone): targeted follow-up questions for the founder.

    Wired up now so the verification loop is a small step from here, not a
    rewrite. Returns the questions; collecting answers + regenerating the
    blueprint is the interactive loop to build into the frontend.
    """
    raw = llm.complete(
        prompts.FOLLOWUP_SYSTEM,
        prompts.FOLLOWUP_USER.format(blueprint=blueprint.to_prompt_block()),
        task="followup",
        max_tokens=llm.scale_tokens(1000),
    )
    data = extract_json(raw)
    return data if isinstance(data, list) else []
