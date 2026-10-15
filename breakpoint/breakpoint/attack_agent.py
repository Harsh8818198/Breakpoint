"""The attack side of claim verification.

Explores a live target over HTTP only -- same interface an attacker would
have -- and tries to falsify one claim. Proposes a proof request when it
concludes falsified, but does not get to decide the verdict itself; the
caller (claim_verifier.replay_and_check) re-runs that exact request
independently before trusting it. See RECEIPT, arXiv 2607.18575, on agents
satisfying a verifier without a reproducible exploit.

LLMClient.complete() is single-turn (system + user -> text), so the ReAct
loop manages its own transcript by re-sending the accumulated conversation
as the user message each turn, rather than relying on a chat-history API.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .llm import LLMClient, extract_json
from . import prompts


@dataclass
class AttackResult:
    concluded: bool
    claimed_falsified: bool
    proof_request: dict | None
    reasoning: str
    turns: int
    transcript: list = field(default_factory=list)


def send_request(base_url: str, path: str, query: dict | None = None) -> tuple[int, Any]:
    """Fires one GET request at a target and returns its parsed response.
    Shared by the live attack loop and the independent replay step, so both
    paths exercise the target the same way.
    """
    qs = f"?{urllib.parse.urlencode(query)}" if query else ""
    url = base_url.rstrip("/") + path + qs
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read()

    try:
        body = json.loads(raw.decode()) if raw else None
    except json.JSONDecodeError:
        body = None
    return status, body


def run_attack_loop(llm: LLMClient, statement: str, api_surface: str,
                     base_url: str, max_turns: int = 6) -> AttackResult:
    system = prompts.ATTACK_SYSTEM
    text = prompts.ATTACK_INTRO.format(statement=statement, api_surface=api_surface, max_turns=max_turns)
    transcript: list[dict] = []

    for turn in range(max_turns):
        raw = llm.complete(system, text, task="attack_turn", max_tokens=llm.scale_tokens(400))
        try:
            action = extract_json(raw)
        except (json.JSONDecodeError, ValueError):
            action = {}

        if action.get("action") == "conclude":
            transcript.append({"turn": turn, "action": action})
            falsified = bool(action.get("falsified"))
            return AttackResult(
                concluded=True,
                claimed_falsified=falsified,
                proof_request=action.get("proofRequest") if falsified else None,
                reasoning=str(action.get("reasoning", "")),
                turns=turn + 1,
                transcript=transcript,
            )

        if action.get("action") == "request" and action.get("method") == "GET" and action.get("path"):
            status, body = send_request(base_url, action["path"], action.get("query"))
            transcript.append({"turn": turn, "action": action, "observed": {"status": status, "body": body}})
            text += (
                f"\n\nYou said: {json.dumps(action)}\n"
                f"Response: status={status} body={json.dumps(body)}\n\n"
                "What's your next action?"
            )
            continue

        transcript.append({"turn": turn, "action": action, "observed": None})
        text += (
            f"\n\nYou said: {json.dumps(action)}\n"
            "That action wasn't understood or isn't allowed. Only GET requests to "
            "the listed endpoints, or a conclude action. Try again."
        )

    return AttackResult(
        concluded=False,
        claimed_falsified=False,
        proof_request=None,
        reasoning="Ran out of turns without concluding.",
        turns=max_turns,
        transcript=transcript,
    )
