"""Runs claim verification against a live target and reports which claims
held and which were falsified.

replay_and_check() is the only place a verdict gets computed -- neither the
attack loop nor the agent's own reasoning decides it (see RECEIPT, arXiv
2607.18575, on agents satisfying a verifier without a reproducible exploit).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .llm import LLMClient
from .attack_agent import AttackResult, run_attack_loop, send_request


@dataclass
class FixtureClaim:
    """A claim against a specific fixture target, with a pure predicate over
    an HTTP response plus the known exploit request kept for regression
    testing. Distinct from claims.Claim (the LLM-extracted kind) -- this one
    is only ever hand-authored against a target you control.
    """
    id: str
    statement: str
    severity: str
    check_response: Callable[[int, object], tuple[bool, str]]
    golden_attempt: dict  # {"path": str, "query": dict | None}


def replay_and_check(claim: FixtureClaim, request: dict, base_url: str) -> dict:
    status, body = send_request(base_url, request["path"], request.get("query"))
    held, note = claim.check_response(status, body)
    return {"status": "held" if held else "falsified", "note": note, "request": request}


def run_golden_regression(claims: list[FixtureClaim], base_url: str) -> dict:
    """Fast, free, no-LLM regression check: replays each claim's known
    exploit attempt and confirms the predicate still reads it correctly.
    """
    results = []
    for claim in claims:
        verdict = replay_and_check(claim, claim.golden_attempt, base_url)
        results.append({
            "id": claim.id, "statement": claim.statement, "severity": claim.severity,
            "status": verdict["status"], "note": verdict["note"],
        })
    return _summarize(results)


def run_agent_claim_verification(llm: LLMClient, claims: list[FixtureClaim], api_surface: str,
                                  start_fixture_fn: Callable[[], object],
                                  max_turns: int = 6) -> dict:
    """Agent-driven verification: for each claim, an LLM explores a fresh
    instance of the target over HTTP only, with no hint which endpoint is
    flawed. A claimed exploit is replayed against a second, independent
    fresh instance before the verdict counts -- the agent's transcript is
    never trusted as proof.
    """
    results = []

    for claim in claims:
        exploration = start_fixture_fn()
        try:
            attack = run_attack_loop(llm, claim.statement, api_surface, exploration.base_url, max_turns)
        finally:
            exploration.close()

        base = {"id": claim.id, "statement": claim.statement, "severity": claim.severity, "turns": attack.turns}

        if not attack.concluded:
            results.append({**base, "status": "inconclusive", "note": attack.reasoning})
            continue

        if not attack.claimed_falsified:
            results.append({**base, "status": "held", "note": f"agent found no violation: {attack.reasoning}"})
            continue

        if not attack.proof_request:
            results.append({**base, "status": "agent_claim_unverified",
                             "note": "agent claimed falsified but gave no proof request"})
            continue

        replay_target = start_fixture_fn()
        try:
            verdict = replay_and_check(claim, attack.proof_request, replay_target.base_url)
        finally:
            replay_target.close()

        confirmed = verdict["status"] == "falsified"
        results.append({
            **base,
            "status": "falsified" if confirmed else "agent_claim_unverified",
            "note": (f"confirmed by independent replay: {verdict['note']}" if confirmed
                     else f"agent claimed falsified, replay did not reproduce it: {verdict['note']}"),
            "proof_request": attack.proof_request,
            "agent_reasoning": attack.reasoning,
        })

    return _summarize(results)


def _summarize(results: list[dict]) -> dict:
    def count(status: str) -> int:
        return sum(1 for r in results if r["status"] == status)

    return {
        "results": results,
        "held_count": count("held"),
        "falsified_count": count("falsified"),
        "inconclusive_count": count("inconclusive"),
        "unverified_count": count("agent_claim_unverified"),
    }
