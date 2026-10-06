"""CLI for the claim-driven verification layer's fixture tests.

Run with:
  python run_fixture.py verify                        # free, no LLM
  python run_fixture.py attack [--max-turns N]         # needs an API key
  python run_fixture.py extract                        # needs an API key

Provider and key are read from .env (default provider: anthropic), same as
run.py and server.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from breakpoint.llm import LLMClient
from breakpoint.claims import extract_claims
from breakpoint.claim_verifier import run_golden_regression, run_agent_claim_verification

from fixtures.target_app.server import start_fixture
from fixtures.target_app.claims_data import claims as fixture_claims, api_surface
from fixtures.target_app.blueprint_data import FIXTURE_BLUEPRINT

_STATUS_BADGE = {
    "held": "HELD              ",
    "falsified": "FALSIFIED         ",
    "inconclusive": "INCONCLUSIVE      ",
    "agent_claim_unverified": "AGENT_UNVERIFIED  ",
}


def run_verify() -> None:
    print("Starting NoteShare fixture...")
    fixture = start_fixture()
    print(f"Fixture running at {fixture.base_url}\n")
    try:
        summary = run_golden_regression(fixture_claims, fixture.base_url)
        _print_results(summary)
    finally:
        fixture.close()


def run_attack(provider: str | None, max_turns: int) -> None:
    llm = LLMClient(provider=provider)
    print(f"Attacking the NoteShare fixture via {llm.provider}, {len(fixture_claims)} claims, "
          f"up to {max_turns} turns each...\n")
    summary = run_agent_claim_verification(llm, fixture_claims, api_surface, start_fixture, max_turns)
    _print_results(summary)


def run_extract(provider: str | None) -> None:
    llm = LLMClient(provider=provider)
    print(f"Extracting claims from the fixture blueprint via {llm.provider}...\n")
    claims = extract_claims(FIXTURE_BLUEPRINT, llm)

    by_category: dict[str, int] = {}
    for c in claims:
        by_category[c.category] = by_category.get(c.category, 0) + 1

    print(f"{len(claims)} claims extracted:")
    for category, count in by_category.items():
        print(f"  {category:<16} {count}")

    print()
    for c in claims:
        badge = "[formal]" if c.formalizable else "[nl]    "
        print(f"{badge} ({c.severity_if_false}) {c.statement}")

    print(f"\nHand-written claims to compare against ({len(fixture_claims)}):")
    for fc in fixture_claims:
        print(f"  ({fc.severity}) {fc.statement}")


def _print_results(summary: dict) -> None:
    for r in summary["results"]:
        print(f"[{_STATUS_BADGE[r['status']]}] ({r['severity']}) {r['statement']}")
        if r.get("proof_request"):
            pr = r["proof_request"]
            q = f" {pr.get('query')}" if pr.get("query") else ""
            print(f"           proof: {pr.get('method', 'GET')} {pr['path']}{q}")
        if r.get("turns"):
            print(f"           turns: {r['turns']}")
        print(f"           {r['note']}\n")

    extra = []
    if summary["inconclusive_count"]:
        extra.append(f", {summary['inconclusive_count']} inconclusive")
    if summary["unverified_count"]:
        extra.append(f", {summary['unverified_count']} agent-claimed-but-unverified")
    print(
        f"{summary['held_count']} held, {summary['falsified_count']} falsified"
        + "".join(extra)
        + f", out of {len(summary['results'])} claims."
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Claim-driven verification layer: fixture tests")
    p.add_argument("mode", choices=["verify", "attack", "extract"])
    p.add_argument("--provider", help="anthropic | openai | gemini (default: BREAKPOINT_PROVIDER or anthropic)")
    p.add_argument("--max-turns", type=int, default=6, help="turn budget per claim for attack mode")
    args = p.parse_args(argv)

    if args.mode == "verify":
        run_verify()
    elif args.mode == "attack":
        run_attack(args.provider, args.max_turns)
    elif args.mode == "extract":
        run_extract(args.provider)


if __name__ == "__main__":
    main(sys.argv[1:])
