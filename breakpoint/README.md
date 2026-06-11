# Breakpoint

Evolutionary adversarial-user simulator. AI agents with distinct personas probe
a product across generations; each generation is asked a *structurally different
question*, so Gen 5 findings are categorically different from Gen 1 — not a
reworded restatement.

This repo is the **core engine** (the moat), built before any UI so the
evolution mechanism can be validated first (the spec's "Critical Success Test").

## Run it in 30 seconds (no API key)

```bash
export BREAKPOINT_PROVIDER=mock
python -m breakpoint.run --validate
```

This runs the whole pipeline on canned data so you can see the plumbing:
blueprint → agents → generations → dedup → evolution tree → report.

## Run it for real

```bash
export BREAKPOINT_PROVIDER=anthropic   # or: openai
export ANTHROPIC_API_KEY=sk-...        # or: OPENAI_API_KEY
python -m breakpoint.run --desc "your product description..." --gens 5 --questions
```

Flags: `--gens N`, `--archetypes N` (subset of the 12 base types),
`--product-specific N`, `--questions` (print interrogation follow-ups),
`--desc-file path`.

## Architecture (maps to spec STEPs 1–5)

```
breakpoint/
  models.py      Blueprint, Agent, Finding (+ BSS severity score)
  llm.py         provider-agnostic client (mock | anthropic | openai) + JSON extract
  prompts.py     all templates — incl. GENERATION_INSTRUCTIONS (the moat)
  blueprint.py   STEP 1  raw description -> Blueprint  (+ interrogate() stub)
  agents.py      STEP 3  archetype + product-specific agents (+ LHS diversity)
  evolution.py   STEP 4  the generational loop with lineage + dedup
  report.py      STEP 5  exec summary, ranked cards, evolution tree
  run.py         CLI
  mockdata.py    canned responses for keyless testing
```

Every module is provider-agnostic and returns plain dataclasses, so wrapping it
in FastAPI later is one thin layer per module.

## What's built vs. next

Built (v0, the risky core):
- Mode 1 input (description → blueprint), interrogation questions
- 12 archetypes + product-specific agent generation
- Gen 1–5 evolutionary loop, lineage tracking, title dedup
- BSS severity scoring, ranked vulnerability cards, evolution tree

Next, in priority order:
1. **Interactive verification loop** (spec POINT 2): collect answers to the
   interrogation questions, regenerate blueprint, read-back + "risks I already
   see", max 3 refine cycles. `blueprint.interrogate()` is already wired.
2. **Semantic dedup**: replace title-normalization with embedding similarity so
   near-duplicate findings across generations are merged properly.
3. **FastAPI + SSE**: stream Gen 1 results live while later gens run
   (the `on_event` callback in `simulate()` is the hook).
4. **Next.js frontend**: persona cards, attack-surface heatmap, interactive
   evolution tree, remediation roadmap.
5. **Mode 3** (codebase connection) as the premium tier.

## Calibration note

`Finding.bss` and the severity bands in `models.py` are tunable. With mock data
they read low; calibrate the thresholds against a few real runs.
