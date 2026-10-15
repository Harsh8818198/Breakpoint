"""Claim extraction -- the unit agents target instead of freeform archetype
roleplay.

A claim is a specific, falsifiable guarantee the product design makes. The
rest of the claim-driven verification layer (attack_agent.py,
claim_verifier.py) exists to falsify or confirm claims, not to roleplay a
persona against the product in general.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from .llm import LLMClient, extract_json
from .models import Blueprint, _id
from . import prompts

_VALID_CATEGORIES = {
    "auth", "rate_limit", "data_isolation", "payment",
    "business_logic", "ux", "compliance", "other",
}
_VALID_SEVERITIES = {"critical", "high", "medium", "low"}


@dataclass
class Claim:
    """A single falsifiable guarantee extracted from a blueprint.

    alpha/beta carry a Beta(alpha, beta) posterior on "this claim holds" --
    a failed falsification attempt nudges beta up slightly (absence of proof
    is weak evidence); a successful one is terminal (status -> falsified).
    """
    statement: str
    category: str = "other"
    feature_refs: list[str] = field(default_factory=list)
    formalizable: bool = False
    predicate: str | None = None
    severity_if_false: str = "medium"
    alpha: float = 1.0
    beta: float = 1.0
    test_count: int = 0
    status: str = "active"  # active | falsified
    id: str = field(default_factory=_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __repr__(self) -> str:
        badge = "[formal]" if self.formalizable else "[nl]"
        return f"Claim({badge} {self.statement!r}, {self.severity_if_false})"


def extract_claims(blueprint: Blueprint, llm: LLMClient) -> list[Claim]:
    """Extract claims from a blueprint via the LLM. Pure -- no DB, no side
    effects, so it can run standalone against a blueprint with no simulation
    context yet.
    """
    raw = llm.complete(
        prompts.CLAIM_SYSTEM,
        prompts.CLAIM_USER.format(blueprint_block=blueprint.to_prompt_block()),
        task="claim_extraction",
        max_tokens=llm.scale_tokens(3000),
    )
    data = extract_json(raw)
    raw_claims = data.get("claims", []) if isinstance(data, dict) else []
    return [c for c in (_normalize(rc) for rc in raw_claims) if c is not None]


def _normalize(raw: dict) -> Claim | None:
    statement = (raw or {}).get("statement")
    if not isinstance(statement, str) or not statement.strip():
        return None

    formalizable = bool(raw.get("formalizable"))
    category = raw.get("category")
    severity = raw.get("severity_if_false")

    return Claim(
        statement=statement.strip(),
        category=category if category in _VALID_CATEGORIES else "other",
        feature_refs=[str(r) for r in raw.get("feature_refs", []) if isinstance(raw.get("feature_refs"), list)],
        formalizable=formalizable,
        predicate=str(raw["predicate"]) if formalizable and raw.get("predicate") else None,
        severity_if_false=severity if severity in _VALID_SEVERITIES else "medium",
    )
