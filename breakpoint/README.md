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

A claim that a protection is **missing or switched off** (no CSRF token, no `httpOnly`, `helmet` commented out) has no
live line to quote. For these the reviewer lists the names the protection would carry in live code, and the check
searches the whole repository itself, whole words only. It accepts the absence only if no live line of any code file uses
those names (a bare `require`/`import` line does not count as a use; docs, tests, manifests and templates are ignored),
and it takes the commented-out lines it finds as the evidence (marked `"kind": "switched_off"`). The impact must still
follow and the defender still runs. It cannot prove absence when the protection exists under a name the reviewer did not
think of; the defender reading the files is the only guard against that.

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
- gemini-3.1-flash-lite, re-run 2026-10-15: kept 12 of 13 real and 0 of 7 false. The one real claim it dropped says
  the session cookie lacks HttpOnly/Secure; those flags exist only in commented-out lines, and the check could not
  yet accept "this protection is absent" as a quotable fact.
- same model, 2026-10-16, after the missing-protection rule above: kept 13 of 13 real and 0 of 7 false. The cookie-flags
  and CSRF claims now pass through the new rule.
- Caveat: these 20 claims were also used to tune the check, and the missing-protection rule was written to fix the miss
  above, so this is not a held-out test. One call in the 2026-10-15 run failed on a provider error.

Before the check existed, hand-grading reports on two of the author's own apps found 1 of 16 and
0 of 17 findings held up against the code. That is why the check exists.

**2. Does the engine find the bugs?** OWASP NodeGoat `c5cb68a`, gemini-3.1-flash-lite, hand-judged:

- engine without code retrieval: 3 of 13 real bugs found, 5 of 12 kept claims false
- engine with code retrieval: 7 of 13 found, 3 of 14 kept claims false
- one plain prompt with the whole source (its claims were not run through the code check): named 10 of 13
  (checked later, see item 4: it still found 10 of 13)

So on a repo small enough to fit in one prompt, the plain prompt found as many bugs as the engine or more.
The retrieval cues were written with NodeGoat in view, so these numbers flatter the engine.

**3. Planted-flaw benchmark** (`python -m breakpoint.bench.harness`): NoteShare is a small app with 4
planted bugs; each claim becomes an exploit script that an executable spec judges. gpt-4o, 5 runs:

- share of tested claims that were real: engine 31-44%, one plain prompt 25-36%
- planted bugs found: engine 1-3 of 4, one plain prompt 3-4 of 4

These runs pre-date the code check and the code retrieval.

**4. Per-route review against one plain prompt** (`--route-review`, below). OWASP NodeGoat `c5cb68a`,
gemini-3.1-flash-lite, one run each, both arms through the same code check, verdicts read by hand from the source
(`bench_runs/route_review/`, including the raw results and one verdict per kept finding):

- one plain prompt (the whole source, one call): 10 of 13 known bugs found; 12 findings kept, none wrong, 2 more real.
  It missed session fixation, the login-error disclosure and the hard-coded secret. Three of its claims hit provider
  errors in the first checking pass and were re-checked; one (ReDoS) errored again and is not counted.
- per-route review (47 reviews plus the code check): 10 of 13 found; 21 findings kept, 5 weak or wrong, 3 more real.
  It missed CSRF, the cookie flags and the hard-coded secret. The mechanical scorer reports 13 of 13 for it; three of
  those credits are wrong (a finding's evidence line happened to fall inside another bug's location range).
- the two found different bugs, so together they cover 12 of 13.
- the route reviewers did propose CSRF and cookie-flag findings, but the code check of that day dropped them as unproven
  (it could not yet accept "this protection is absent"; see item 1). After the missing-protection rule, the six dropped
  claims (three worded CSRF, cookie flags, two about security headers) all hold when re-checked on 2026-10-16. That was
  a re-check of those six, not a re-run of the review, so the 10 of 13 above stands as measured; with those findings
  kept it would be 12 of 13 by my reading (only the hard-coded signing secret missed).

**5. Pilot of the evaluation harness** (2026-10-18). One plain-prompt run per row, gemini-3.1-flash-lite, every kept finding
read by hand (`bench_runs/eval_pilot/`: runs, verdicts and summaries). One run is not a measurement: this shows that the
harness works and which way a leak points.

| Set and variant | Known bugs found (adjudicated) | Kept issues that are real | Calls | Est. tokens |
|---|---|---|---|---|
| NodeGoat raw (answers in comments and tutorial) | 11 of 13 | 12 of 13 | 45 | 525k |
| NodeGoat, hint comments and tutorial removed | 9 of 13 | 11 of 13 | 46 | 407k |
| NodeGoat, all comments removed | 6 of 13 | 10 of 10 | 46 | 395k |
| DVNA, docs and learn pages removed (held out) | 12 of 18 | 12 of 12 | 46 | 354k |

- The same prompt found fewer bugs as the answer key was taken out: 11, 9, 6. With one run per row the size of the drop is
  uncertain. Part of the last drop is the code check, which proves "this protection is missing" claims (CSRF, cookie flags) only
  from commented-out copies, and those are gone in that variant.
- The mechanical score overcredited in every row (12, 10, 9 and 14 against 11, 9, 6 and 12).
- Cost: the plain prompt is one generating call; checking its 15 claims took about 45 calls and most of the estimated tokens.
- DVNA is a public teaching app that models have probably seen, so 12 of 18 says little about real code. The wall-clock for the
  NodeGoat hints row is not reliable (the machine slept during it).

**6. Real flaws fixed after the model existed** (2026-10-24 and 25). 22 sets built from GitHub security advisories
(`eval_sets/history/`): small npm and PyPI libraries, each pinned one commit before the maintainers' fix and labelled by it, fix
committed after gemini-3.1-flash-lite was released. The plain prompt three times per set, every candidate read by hand
(`bench_runs/history_pilot/RESULTS.md`: setup, selection log, readings, survivors).

- The plain prompt named the maintainers' flaw clearly in 6 of 66 runs (4 of 22 sets in at least one run); counting a claim in the
  right place and class but vaguer, 23 of 66 runs (12 of 22 sets). The teaching apps above gave 6 to 11 of 13 and were not a guide.
- The code check kept 6 of 7 candidates that described the flaw and 0 of 19 vaguer ones. Run again on 9 of them it changed its
  decision on 2, one of them a true flaw, so one check run per claim is not enough.
- On all 15 candidates of four sets it kept 10 of 60. None of the 10 is a vulnerability: six are accurate observations about a
  feature or a local tool, four are wrong. Kept means the code does what the claim says, not that it is a vulnerability.
- One reader for every reading, one model for finder and checker, small repositories, nothing tuned on these sets.

**What this supports:** reported findings come with quoted evidence and few false claims.
**What it does not support:** that the engine, or the per-route review, finds more bugs than one prompt does; or (item 6)
that a kept finding is a vulnerability worth reporting. On a repo
this small the whole source fits in one prompt, so the per-route review matched its recall with more noise and about
fifty times as many model calls. Whether it pays off on a repo too big for one prompt is untested. Closing that gap
is the open work: raising how many real bugs get found, not how many false ones get through.

## Route map (Express, work in progress)

```bash
python -m breakpoint.routemap path/to/express/app          # add --json for machine-readable output
python -m tests.eval_routemap --codebase path/to/NodeGoat   # does each known bug's code sit inside some route's node?
```

Splits an Express app into one unit per route: where it is registered, the protections in front of it (login
check, admin check), its handler, and the code the handler calls one or two hops down. It also lists protections
that were switched off (a commented-out copy of the route with an extra check, or a commented-out `app.use(...)`),
and which routes read request input or reach `eval`, a redirect, a database query or an outbound request.
It reads source text only: no model is called and no code is run. `--route-review` (next section) builds on it.

Checked so far: NodeGoat gives 20 routes, and all 13 known bugs fall inside some node (9 inside a route's node,
4 in app-wide setup such as session settings and CSRF). DVNA, which the mapper was not written against, gives 32
routes, the same count as a plain text search for route registrations. Caveats: the NodeGoat check was used while
writing it; "inside a node" means the code was in front of a reviewer, not that a reviewer finds the bug; it does not
understand `app.route()` chains, dynamic `require`, routes built in loops or non-Express frameworks (it returns fewer
routes, never invented ones).

## Per-route review (Express, experimental)

```bash
python -m breakpoint.run --route-review review.json --codebase path/to/express/app
python -m tests.score_report review.json          # NodeGoat only: which of the 13 known bugs the kept findings point at
```

For each route the route map finds, a model reviews only that route's code (registration, the protections in front of it,
the handler, what the handler calls) and answers only the questions that route's own facts allow: access control
(every route); untrusted input (routes that read request input and reach `eval`, a shell, a query, a file or the
response); redirects and outbound requests; credentials and sessions; plus one app-wide review of cookie flags, the
signing secret, CSRF, template escaping and security headers. Every finding must cite the exact vulnerable lines, the
citation is checked against the file, duplicates are merged, and the survivors go through the same code check as
everything else. The reviews are saved before checking starts, so a provider failure does not lose them
(check them later with `--verify-report`). `--review-max-calls N` caps the spend (default 150); NodeGoat takes 47.
`--no-verify` skips the code check. Express only: any other repo stops with a message.

It is a measured experiment, not a proven improvement; see "Measured results", item 4.

## Evaluation harness

How to tell whether a way of finding bugs is better than another, on repositories whose bugs are known, with every
number carrying its caveats. Needs an editable install (`pip install -e .`) because the sets live in `eval_sets/`.

```bash
breakpoint-eval list
breakpoint-eval check nodegoat                              # every known bug still has live code in every variant
breakpoint-eval info dvna --variant clean                   # size, routes, does it fit one prompt, rough calls per run
breakpoint-eval run dvna --variant clean --arm plain --arm route-review --runs 3
breakpoint-eval run dvna --variant clean --arm import:claude-review.json   # a result made elsewhere: our JSON or SARIF
breakpoint-eval adjudicate --set dvna --variant clean       # writes the issues a person must read and judge
breakpoint-eval report --set dvna --variant clean           # the comparison, with the caveats that apply
breakpoint-eval harvest --count 24                          # real flaws: build sets from security advisories with a fix commit
breakpoint-eval history --arm plain                         # one table over every advisory set that has runs
```

- **Arms.** `plain` (one prompt with as much source as fits), `route-review`, and `import:<file>` for anything produced
  elsewhere, such as a saved Claude Code `/security-review`, Codex Security, Semgrep or CodeQL result. Every arm's
  candidates go through the same code check, so none wins by being easier to believe.
- **Repeated runs.** Each run is saved as it finishes (`eval_runs/<set>__<variant>/<arm>/run_<n>.json`); a provider failure
  never loses a finished run and re-running the command resumes. One run is not a measurement, so the report flags fewer
  than three.
- **Two scores.** *Mechanical*: a bug counts as found when a kept finding's evidence line falls inside its labelled lines.
  *Adjudicated*: a person reads each distinct issue once (real / false / mixed, and which known bug) and the verdict is
  reused for every run and arm that produces the same issue. Issues without a verdict are reported as undecided. The
  mechanical score has credited bugs a finding never claimed.
- **Cost.** Calls, estimated tokens (characters / 4) and seconds for the arm and for the checking, and calls per bug found.
- **Leaks.** Teaching apps announce their own bugs in comments, tutorials and solution files. Each set has cleaned variants
  (see `eval_sets/README.md`); run an arm on `raw` and on a cleaned variant to see what the leak is worth.

The three sets shipped (NodeGoat as the dev set, DVNA and Juice Shop held out) are all public teaching apps that models
have probably seen, labelled by one reader or taken from the maintainers' own markers. They check the harness and measure
leakage; they do not show how Breakpoint does on real code. The advisory sets (`eval_sets/history/`, described in
`eval_sets/README.md`) are the real-code check: maintainers' own fixes, made after the model existed. `eval_sets/README.md` also
lists what is still missing.

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
  routemap.py    Express app -> routes, protections, handlers, callees (no model calls)
  routereview.py per-route, per-question model review on top of the route map (--route-review)
  usage.py       counts model calls, estimated tokens and seconds (MeteredLLM)
  evaluation/    breakpoint-eval: evaluation sets, cleaned variants, arms, repeated runs, scoring, adjudication
  baseline.py    the single-prompt comparison (--baseline)
  cvg.py         causal vulnerability graph (shared root causes, minimal fix set)
  report.py      exec summary, ranked cards with evidence, rejected claims, evolution tree
  run.py         CLI
```

## Calibration note

`Finding.bss` and the severity bands in `models.py` are tunable and are scored by
the model; calibrate them against real runs before relying on the ranking.
