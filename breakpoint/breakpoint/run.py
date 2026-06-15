"""CLI runner.

  python -m breakpoint.run --desc "your product..."
  python -m breakpoint.run --desc-file product.txt --gens 5
  python -m breakpoint.run --check                      # verify API key works

Provider and key are read from .env (default provider: anthropic).
"""

from __future__ import annotations

import argparse
import sys

from .llm import LLMClient
from .blueprint import build_blueprint, interrogate
from .agents import build_population
from .evolution import simulate, _norm
from .report import render_report
from .models import Blueprint, Finding
from . import prompts

_MAX_GENS = max(prompts.GENERATION_INSTRUCTIONS)

DESC_TEMPLATE = """\
# Breakpoint Description Template — fill every section before running.
# Vague or omitted fields cause the model to invent mechanics and hallucinate findings.
# Delete the comment lines when you paste into --desc or save as a .txt file.

Product name: [e.g. "Acme Workflows"]
Product type: [SaaS web app | mobile app | API | CLI | ...]
Domain: [e.g. "AI automation", "FinTech", "EdTech"]
Stage: [Pre-launch | Beta | Live]

AUTHENTICATION (name the exact provider — "OAuth" alone is too vague):
- Methods: [e.g. "Google OAuth (one account per verified Google email), email+password"]
- Session: [e.g. "JWT, 24h expiry, httpOnly refresh cookie"]
- Password reset: [e.g. "email link, expires in 1h"]

TIERS AND LIMITS (be exact — placeholder values like "X/month" cause hallucinated limits):
- Free tier: [e.g. "1 pipeline max, 1,000 actions/month, 1 KB, 1 integration, 1 GB storage"]
- Paid tiers: [list each with price and exact limits]
- How limits enforced: [server-side counter | client-side | honor system]
- On limit hit: [hard block | soft warn | overage charge]

WHAT THE PLATFORM STORES ON USERS' BEHALF:
- Credentials: [e.g. "users supply their own OpenAI and Anthropic API keys, stored encrypted"]
- User data: [e.g. "pipeline configs, KB document chunks, integration OAuth tokens"]
- Third-party tokens: [e.g. "Slack OAuth tokens, Google Drive refresh tokens"]

WHAT THE PLATFORM CAN DO:
- Outbound HTTP: [yes — pipelines can call arbitrary URLs | no]
- LLM calls: [which models, on whose API key — user-supplied or platform key]
- File access: [what the platform reads or writes on users' behalf]
- Integrations: [list them and how they auth, e.g. "Slack via OAuth, Stripe via API key"]

DATA ISOLATION:
- Tenant model: [single-tenant | multi-tenant shared DB | multi-tenant isolated schema]
- Can users see other users' data? [never | only if explicitly shared | yes via X]

SECURITY POSTURE:
- Certifications: [e.g. "SOC 2 Type II, GDPR, HIPAA"] or "none"
- Access control: [RBAC roles | no roles | SSO only]
- Deployment: [shared cloud | single-tenant cloud | VPC | on-prem]

KNOWN GAPS (things not yet decided or implemented — be honest):
- [list anything undefined, e.g. "rate limiting not yet implemented on pipeline API"]
"""

DEMO_DESC = (
    "StudyBuddy AI is an AI tutoring web app for college students. Upload your "
    "notes, ask questions, get AI explanations, take AI-generated practice "
    "quizzes, and study with friends in group rooms. Google sign-in only. Free "
    "users get 5 questions/day; Pro is unlimited and can generate quizzes."
)


import json

def _stream(kind: str, payload) -> None:
    if kind == "generation_start":
        print(f"\n--- Generation {payload['generation']} running ---")
    elif kind == "finding":
        print(f"   + {payload.discovered_by:>16}: {payload.title}")
    elif kind == "generation_end":
        print(f"   = kept {payload['kept']}/{payload['raw']} after dedup")


def _pipeline(description: str | None, gens: int, archetypes: int | None,
              product_specific: int, show_questions: bool, interactive: bool = False,
              codebase: str | None = None, docs: list[str] | None = None) -> tuple[Blueprint, list[Finding]]:
    llm = LLMClient()
    print(f"Provider: {llm.provider} | Model: {llm.model}")

    if codebase:
        from .blueprint import build_blueprint_from_codebase
        bp = build_blueprint_from_codebase(codebase, llm)
    elif docs:
        from .blueprint import build_blueprint_from_documents
        bp = build_blueprint_from_documents(docs, llm)
    elif description:
        if interactive:
            print("\n[1/4] Decomposing product into initial blueprint...")
            bp = build_blueprint(description, llm)
            print(f"      {bp.name} | actors={len(bp.actors)} "
                  f"surface={len(bp.attack_surface)} unknowns={len(bp.known_unknowns)}")

            print("\n[Interactive] Starting follow-up interrogation...")
            questions = interrogate(bp, llm)
            if not questions:
                print("      No follow-up questions needed.")
                refined_desc = description
            else:
                print("\n=======================================================")
                print("  BREAKPOINT INTERROGATION COMMAND CENTER")
                print("=======================================================\n")
                print("Please answer the following mechanical questions to refine the blueprint:")
                qa_blocks = []
                for i, q in enumerate(questions, 1):
                    print(f"\n[Question {i}/{len(questions)}] {q}")
                    try:
                        ans = input("Answer: ").strip()
                    except (KeyboardInterrupt, EOFError):
                        print("\nInterrogation interrupted. Proceeding with current details.")
                        break
                    if ans.lower() in ("exit", "quit", "done"):
                        print("\nInterrogation ended by user.")
                        break
                    if ans:
                        qa_blocks.append(f"Q: {q}\nA: {ans}")
                
                if qa_blocks:
                    refined_desc = description + "\n\nAdditional mechanical details provided by user:\n" + "\n\n".join(qa_blocks)
                    print("\n[1b/4] Refining product blueprint based on your answers...")
                    bp = build_blueprint(refined_desc, llm)
                    print(f"      {bp.name} (refined) | actors={len(bp.actors)} "
                          f"surface={len(bp.attack_surface)} unknowns={len(bp.known_unknowns)}")
                else:
                    refined_desc = description

            description = refined_desc
        else:
            print("\n[1/4] Decomposing product into blueprint...")
            bp = build_blueprint(description, llm)
            print(f"      {bp.name} | actors={len(bp.actors)} "
                  f"surface={len(bp.attack_surface)} unknowns={len(bp.known_unknowns)}")

            if show_questions:
                print("\n[1b] Interrogation follow-ups Breakpoint would ask:")
                for q in interrogate(bp, llm):
                    print(f"      ? {q}")
    else:
        raise ValueError("Must provide either --desc, --desc-file, --codebase, or --docs.")

    print("\n[2/4] Generating agent population...")
    agents = build_population(bp, llm, total_agents=10 if archetypes is None else (archetypes + product_specific))
    print(f"      {len(agents)} agents")

    print("\n[3/4] Running evolutionary simulation...")
    findings = simulate(bp, agents, llm, generations=gens, on_event=_stream)
    return bp, findings


def run(description: str | None, gens: int, archetypes: int | None, product_specific: int,
        show_questions: bool, interactive: bool = False, output: str | None = None,
        codebase: str | None = None, docs: list[str] | None = None) -> str:
    bp, findings = _pipeline(description, gens, archetypes, product_specific, show_questions, interactive, codebase, docs)
    print("\n[4/4] Report\n")
    report = render_report(bp, findings)
    print(report)

    if output:
        try:
            if output.lower().endswith(".json"):
                data = {
                    "blueprint": bp.to_dict(),
                    "findings": [f.to_dict() for f in findings]
                }
                with open(output, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
                print(f"\n[+] Saved JSON report to {output}")
            else:
                with open(output, "w", encoding="utf-8") as fh:
                    fh.write(report)
                print(f"\n[+] Saved text report to {output}")
        except OSError as e:
            print(f"\n[error] Failed to write report to {output}: {e}")

    return report


def check() -> None:
    """Verify the API key and provider work by building a minimal blueprint."""
    llm = LLMClient()
    print(f"Checking {llm.provider} / {llm.model} ...")
    try:
        bp = build_blueprint("A simple to-do list app with user accounts.", llm)
        print(f"OK — blueprint returned: {bp.name!r} ({bp.domain})")
    except Exception as e:
        sys.exit(f"FAIL: {e}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description="Breakpoint: evolutionary adversarial-user simulation engine")
    p.add_argument("--desc", help="product description")
    p.add_argument("--desc-file", metavar="PATH",
                   help="path to a text file containing the product description")
    p.add_argument("--codebase", help="path to local codebase directory to scan (Mode 3)")
    p.add_argument("--docs", nargs="+", help="paths to one or more document files to parse (Mode 2)")
    p.add_argument("--gens", type=int, default=3,
                   help=f"number of generations to run (1-{_MAX_GENS}, default 3)")
    p.add_argument("--archetypes", type=int, default=7,
                   help="how many of the 12 base archetypes to use (default: 7)")
    p.add_argument("--product-specific", type=int, default=3,
                   help="number of product-specific agents to generate (default 3)")
    p.add_argument("--questions", action="store_true",
                   help="print interrogation follow-ups after the blueprint step")
    p.add_argument("--interactive", action="store_true",
                   help="run an interactive follow-up interrogation in terminal to refine details")
    p.add_argument("--output", metavar="PATH",
                   help="save report to a file (saves structured JSON if path ends in .json)")
    p.add_argument("--check", action="store_true",
                   help="verify API key works with a quick test call, then exit")
    p.add_argument("--template", action="store_true",
                   help="print a structured description template and exit")
    args = p.parse_args(argv)

    if args.check:
        check()
        return

    if args.template:
        print(DESC_TEMPLATE)
        return

    if not 1 <= args.gens <= _MAX_GENS:
        sys.exit(f"--gens must be between 1 and {_MAX_GENS} (got {args.gens})")

    desc = args.desc
    if args.desc_file:
        try:
            with open(args.desc_file, encoding="utf-8") as fh:
                desc = fh.read()
        except OSError as e:
            sys.exit(f"Cannot read {args.desc_file!r}: {e}")
            
    if not desc and not args.codebase and not args.docs:
        desc = DEMO_DESC
        print("(no input given; using built-in StudyBuddy demo)\n")

    run(desc, args.gens, args.archetypes, args.product_specific, args.questions, args.interactive, args.output, args.codebase, args.docs)


if __name__ == "__main__":
    main(sys.argv[1:])
