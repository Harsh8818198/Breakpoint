"""Core data models for Breakpoint.

These map 1:1 to the Product Blueprint, Agent, and Vulnerability structures
in the spec. Kept as plain dataclasses so they serialize cleanly to JSON for
a FastAPI layer later.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any
import uuid


def _id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Flow:
    name: str
    steps: list[str]

    def __repr__(self) -> str:
        return f"Flow({self.name!r}, steps={len(self.steps)})"


@dataclass
class Blueprint:
    """Universal output of all input modes (spec: 'The Product Blueprint')."""
    name: str
    type: str
    domain: str
    stage: str
    actors: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)
    mechanical_details: list[str] = field(default_factory=list)
    known_unknowns: list[str] = field(default_factory=list)
    attack_surface: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        """Compact, LLM-readable rendering injected into every agent call."""
        lines = [
            f"PRODUCT: {self.name} ({self.type}, domain={self.domain}, stage={self.stage})",
            "ACTORS: " + "; ".join(self.actors),
            "RESOURCES: " + "; ".join(self.resources),
            "BOUNDARIES: " + "; ".join(self.boundaries),
            "FLOWS:",
        ]
        for f in self.flows:
            lines.append(f"  - {f.name}: " + " -> ".join(f.steps))
        lines.append("MECHANICAL DETAILS: " + "; ".join(self.mechanical_details))
        lines.append("KNOWN UNKNOWNS (highest-value, undefined behavior): "
                     + "; ".join(self.known_unknowns))
        lines.append("ATTACK SURFACE: " + "; ".join(self.attack_surface))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __repr__(self) -> str:
        return (f"Blueprint({self.name!r}, domain={self.domain!r}, "
                f"actors={len(self.actors)}, surface={len(self.attack_surface)})")


@dataclass
class Agent:
    """A diverse threat actor (spec: 'Agent Architecture v2')."""
    name: str
    archetype: str
    age: int
    backstory: str
    motivation: str
    goal: str
    knowledge: list[str] = field(default_factory=list)
    willing_to: list[str] = field(default_factory=list)
    unwilling_to: list[str] = field(default_factory=list)
    personality: dict[str, float] = field(default_factory=dict)
    id: str = field(default_factory=_id)

    def to_prompt_block(self) -> str:
        return (
            f"You are {self.name}, age {self.age}. Archetype: {self.archetype}.\n"
            f"Backstory: {self.backstory}\n"
            f"Your motivation: {self.motivation}\n"
            f"Your goal with this product: {self.goal}\n"
            f"You know about: {', '.join(self.knowledge)}\n"
            f"You are willing to: {', '.join(self.willing_to)}\n"
            f"You will NOT: {', '.join(self.unwilling_to)}"
        )

    def __repr__(self) -> str:
        return f"Agent({self.name!r}, archetype={self.archetype!r})"


@dataclass
class Finding:
    """A discovered vulnerability with evolutionary lineage."""
    title: str
    generation: int
    discovered_by: str          # agent name
    description: str
    steps_to_exploit: list[str] = field(default_factory=list)
    impact: str = ""
    evolved_from: list[str] = field(default_factory=list)  # parent finding titles
    attack_category: str = ""       # auth | authz | rate_limiting | data_privacy | billing | injection | crypto | config | supply_chain | ux
    confidence: float = 1.0         # 0-1: how grounded in stated blueprint facts vs assumed
    # Raw 0-10 sub-scores from the agent, used to compute BSS.
    exploitability: float = 0.0
    impact_score: float = 0.0
    spread: float = 0.0
    fix_difficulty: float = 1.0
    id: str = field(default_factory=_id)

    @property
    def bss(self) -> float:
        """Breakpoint Severity Score, normalized to 0-10 (spec formula).

        Raw (E x I x S) ranges 0..1000; dividing by 100 puts it on a 0..10 band
        when fix difficulty is 1, then fix difficulty scales it down further.
        """
        fd = min(max(self.fix_difficulty, 1.0), 5.0)  # cap at 5 — hard-to-fix ≠ low severity
        return round((self.exploitability * self.impact_score * self.spread) / (fd * 100), 2)

    @property
    def severity_band(self) -> str:
        s = self.bss
        if s >= 3.0:
            return "CRITICAL"
        if s >= 1.5:
            return "HIGH"
        if s >= 0.7:
            return "MEDIUM"
        return "LOW"

    @property
    def fix_priority(self) -> str:
        """Quick triage label based on impact vs fix cost."""
        if self.impact_score >= 7 and self.fix_difficulty <= 3:
            return "FIX NOW"
        if self.impact_score >= 5:
            return "PLAN FIX"
        return "MONITOR"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bss"] = self.bss
        d["severity_band"] = self.severity_band
        d["fix_priority"] = self.fix_priority
        return d

    def __repr__(self) -> str:
        conf = f" conf={self.confidence:.1f}" if self.confidence < 1.0 else ""
        cat = f" [{self.attack_category}]" if self.attack_category else ""
        return (f"Finding({self.title!r}, gen={self.generation}, "
                f"bss={self.bss}, {self.severity_band}{cat}{conf})")
