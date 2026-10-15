# Breakpoint

Evolutionary adversarial-user simulator. AI agents with distinct personas probe
a product across generations; each generation is asked a *structurally different
question* (single feature, then combinations, then systemic abuse, ...).

For a **codebase**, every claim is then checked against the real source before it
can appear in the report (see "Code verification" below).

Status: the code check is the part that has been measured and works. Whether the
persona and generation structure finds more real bugs than one plain prompt is not
shown yet; see "Measured results" below.

## Run it

Needs Python 3.10+ and, to scan a git URL, `git`. The CLI has no third-party dependencies.

```bash
pip install -e .                       # adds the `breakpoint-scan` command; `python -m breakpoint` also works
export BREAKPOINT_PROVIDER=openai      # or: anthropic | gemini   (or put these in a .env file)
export OPENAI_API_KEY=sk-...           # or ANTHROPIC_API_KEY / GEMINI_API_KEY
breakpoint-scan --check                # confirm the key works

# From a product description
breakpoint-scan --desc "your product description..." --gens 3

# From a codebase: a local folder or a git URL (this is the verified mode)
breakpoint-scan --codebase path/or/https://github.com/you/repo --gens 3 --output report.json
```

A codebase run makes roughly 200 model calls, so mind your provider's rate limit (Gemini's free tier
allows 500 requests a day). `python -m breakpoint.run ...` is the same command without installing.
The web server (`server.py`) is optional: `pip install -e ".[server]"`.

Flags: `--gens N`, `--archetypes N`, `--product-specific N`, `--questions`,
`--desc-file path`, `--docs a.pdf b.md`, `--interactive`, `--output file[.json]`,
`--fixed "title" ...` / `--fixed-file report.json` (skip already-patched issues),
`--no-retrieval` / `--no-verify` (codebase mode: turn the code retrieval / code check off).

## Code retrieval (codebase mode)

The blueprint is a summary written from at most 35 files x their first 5,000 characters, so
most of the code never reached an agent. Each agent is now also given the real source for
the attack category it was assigned:

1. One pass over the read-only source index scores every line against cues for each category
   (dangerous operations such as `eval(`, a redirect or an HTTP client fed by request input;
   session and cookie settings; hashing; access checks; the names of security controls).
   Comment lines count for little, and third-party, test, documentation and generated files,
   and code merely printed on a page (`<pre>`), are not retrieved. No model is called.
2. Nearby hits become *regions*. Agents get the best regions for their category as line-numbered
   source (`12c|` = a comment, not active code), about 20,000 characters each.
3. Agents that share a category get different regions, and code earlier verified findings
   already point at is shown less, so later generations look somewhere new.
4. Agent slots go to categories in proportion to how much unexamined code each has; a category
   the repository has nothing for gets none.
5. A **control search** is added: for the protections the category depends on (CSRF, session
   regeneration, cookie flags, password hashing, ...) where each one is in server code, only in a
   template or dependency list, or only in a comment. A missing protection becomes a lead to check.
6. Agents cite `file:line` plus the line itself. A citation is kept only if that line really exists
   in the file named (comments do not count); it then also tells the verifier which file to show its
   judge. It proves nothing by itself: the code check below is unchanged and every finding still has to pass it.

What this does **not** do: it is keyword steering, not program analysis. It cannot follow data
flow across files, and a bug whose code uses none of the cues will not be retrieved. The cues were written
with OWASP NodeGoat's bug classes in view, so NodeGoat numbers flatter it; test on a repo you did not tune on.

## Does the engine beat one plain prompt?

```bash
# the plain alternative: ask the same model ONCE for the 15 most serious vulnerabilities, with the repo's source in the prompt
python -m breakpoint.run --baseline baseline.json --codebase path/to/repo        # add --baseline-context blueprint for the old 35 x 5,000-character sample
# check them with exactly the same code check the engine's findings go through
python -m breakpoint.run --verify-report baseline.json --codebase path/to/repo --output baseline_verified.json
# the engine, with and without code retrieval
python -m breakpoint.run --codebase path/to/repo --gens 3 --output engine.json
python -m breakpoint.run --codebase path/to/repo --gens 3 --no-retrieval --output engine_blueprint_only.json
```

For OWASP NodeGoat (commit `c5cb68a`) the 13 real bugs are listed in `tests/fixtures/nodegoat_labeled_claims.json`
and where they live in `tests/fixtures/nodegoat_gold_locations.json`:

```bash
python -m tests.score_report engine.json            # how many of the 13 the kept findings point at, plus every kept finding that matched nothing
python -m tests.eval_retrieval --codebase path/to/NodeGoat   # offline, no key: was each bug's code in front of an agent?
```

The scorer matches on where a finding's evidence points, not on what it says. Read the printed list of
unmatched findings before quoting a number: each is a real bug the label set lacks or a false claim that got through.

## Code verification (codebase mode)

Agents reason from a short written summary of the code, so on their own they often
claim a protection is missing when it is a few lines further down. Breakpoint
therefore checks every claim against the real files:

1. **Locate** the files and symbols the claim is about.
2. **Judge**: a reviewer reads those files and must quote the vulnerable lines.
3. **Mechanical check**: each quote must exist verbatim in the file it names, and
   gets its true line number. A verdict with no real quote counts for nothing.
4. **Defend**: a second pass reads the confirming file(s) in full, plus the
   functions they call, and tries to find a protection that defeats the claim.

Only claims that survive are reported, each with `file:line` evidence. The report
also lists what was rejected and why, and the JSON has a `verification` block
(`checked / confirmed / refuted / unverified / errors`).

- `--no-verify` turns the check off (findings are then unproven and the report says so).
- `--verify-report report.json --codebase <path>` re-checks any saved report against code.
- Secret files (`.env`, `*.pem`, `*key*.hex`, ...) are never read, and secret-looking
  values are redacted before anything is shown to a model or written to a report.

What the check does **not** do: it reads code, it does not run it, so it cannot
prove an exploit works at runtime; it is tuned to avoid false claims, so it may
drop real but hard-to-prove ones; severity (BSS) is still scored by the model.
The check and the agents currently share one model, so a flaw both are blind to
can get through.

## Measured results

Every number below is on a repo whose real bugs are known, hand-checked, small, and from one run
per arm unless it says otherwise. Read the caveats before quoting any of it.

**1. Does the code check throw out false claims?** On the 20 labelled NodeGoat claims (13 real, 7 false):

- gpt-4o kept 10 of 13 real and 0 of 7 false. gpt-4.1 kept 9 of 13 and 0 of 7 (measured 2026-10-13).
- gemini-3.1-flash-lite, re-run 2026-10-15 with the final code: kept 12 of 13 real and 0 of 7 false. The one
  real claim it dropped says the session cookie lacks HttpOnly/Secure; those flags exist only in commented-out
  lines, and the check does not yet accept "this protection is absent" as a quotable fact.
- Caveat: these 20 claims were also used to tune the check, so this is not a held-out test. One call in this run
  failed on a provider error (the claim was still refuted by the earlier step).

Before the check existed, hand-grading reports on two of the author's own apps found 1 of 16 and
0 of 17 findings held up against the code. That is why the check exists.

**2. Does the engine find the bugs?** OWASP NodeGoat `c5cb68a`, gemini-3.1-flash-lite, hand-judged:

- engine without code retrieval: 3 of 13 real bugs found, 5 of 12 kept claims false
- engine with code retrieval: 7 of 13 found, 3 of 14 kept claims false
- one plain prompt with the whole source (its claims were not run through the code check): named 10 of 13

So on a repo small enough to fit in one prompt, the plain prompt found as many bugs as the engine or more.
The retrieval cues were written with NodeGoat in view, so these numbers flatter the engine.

**3. Planted-flaw benchmark** (`python -m breakpoint.bench.harness`): NoteShare is a small app with 4
planted bugs; each claim becomes an exploit script that an executable spec judges. gpt-4o, 5 runs:

- share of tested claims that were real: engine 31-44%, one plain prompt 25-36%
- planted bugs found: engine 1-3 of 4, one plain prompt 3-4 of 4

These runs pre-date the code check and the code retrieval.

**What this supports:** reported findings come with quoted evidence and few false claims.
**What it does not support:** that the engine finds more bugs than one prompt does. Closing that gap is the
open work: raising how many real bugs get found, not how many false ones get through.

## Tests

```bash
python -m unittest discover -s tests -t .
```

The suite uses scripted fake models (no key, no network).

## Architecture

```
breakpoint/
  models.py      Blueprint, Agent, Finding (+ BSS severity score, verification evidence)
  llm.py         provider-agnostic client (anthropic | openai | gemini) + JSON extract
  prompts.py     all templates — incl. GENERATION_INSTRUCTIONS and the verifier prompts
  blueprint.py   intake: description / documents / codebase -> Blueprint
  agents.py      archetype + product-specific agents (+ LHS diversity)
  evolution.py   the generational loop with lineage, dedup, and the verifier hook
  codeindex.py   read-only index of a repo: secret filtering, redaction, search, quote checking
  coderetrieval.py  per-agent retrieval of real source for the agent's attack category (+ control search, citation check)
  codeverify.py  the locate / judge / mechanical-check / defend verifier
  baseline.py    the single-prompt comparison (--baseline)
  cvg.py         causal vulnerability graph (shared root causes, minimal fix set)
  report.py      exec summary, ranked cards with evidence, rejected claims, evolution tree
  run.py         CLI
```

## Calibration note

`Finding.bss` and the severity bands in `models.py` are tunable and are scored by
the model; calibrate them against real runs before relying on the ranking.
