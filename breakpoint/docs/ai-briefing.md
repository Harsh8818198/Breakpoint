# Breakpoint: briefing for an AI advisor

Written 2026-10-24. Paste this whole document to an AI and ask your question after it. Every number below was measured on small tests and the limits are stated. Please do not round them up.

## 1. What the product is

Breakpoint is an open-source command-line tool (Python, no required dependencies, public repo Harsh8818198/Breakpoint, branch `backend`). You point it at a codebase. Language-model agents look for security problems. A finding is only reported if it survives a check against the real code: the finding must quote the vulnerable lines, and the quote is mechanically checked to exist as live code, not a comment. A refuted finding can appeal, and a separate defender step argues against it. For "this protection is missing" claims, it proves the absence by searching the code for every name the protection could have.

The idea in one line: an agent that hands you proven findings with evidence, not a long list of guesses.

It started as something different: a simulation engine that stress-tests a product idea with 12 persona agents. That engine's reports were not trustworthy (see section 3), so the project moved to verified code findings. The goal the founder confirmed is automated security research, where a tool does the work of a researcher and shows proof.

## 2. What is built

- A verifier for security claims (locate the code, judge it, check the quote, appeal, defender, absence-by-search).
- A route mapper for Express apps that works without any model calls. It lists routes, their protections, handlers and dangerous operations.
- A per-route reviewer: one route, one kind of problem at a time (authorization, injection, outbound requests, sessions), plus one app-wide review.
- An evaluation tool (`breakpoint-eval`): pinned open-source test repos, copies with hints removed, repeated resumable runs, call and token counting, scoring by hand-checked verdicts, and import of other tools' results (JSON or SARIF) for comparison.
- 186 passing tests. The only model provider that currently works is Gemini flash-lite on the free tier (about 500 calls a day). The OpenAI key is invalid.

## 3. What we measured

- **Old engine on the founder's own apps:** 1 of 16 findings real on one product and 0 of 17 on another. The agents had only seen a summary of the code and made claims about code they had not read.
- **Verifier on 20 labelled claims about NodeGoat (13 real, 7 false):** with GPT-4o it kept 10 of 13 real and 0 of 7 false. With Gemini flash-lite after the absence fix it kept 13 of 13 real and 0 of 7 false. Caveat: we tuned the verifier on these claims, so this is not a held-out result.
- **Earlier head-to-head on a small app (NoteShare, GPT-4o, 5 runs):** the engine's findings were 31–44% real and it found 1–3 of 4 planted bugs. A plain single prompt was 25–36% real and found 3–4 of 4. The engine did not beat one prompt.
- **NodeGoat, hand-checked, Gemini flash-lite, one run each:** a plain prompt plus our code check found 10 of 13 known bugs (12 findings kept, none wrong). The per-route reviewer also found 10 of 13, with 21 findings kept and 5 of those weak or wrong, at roughly 50 times the number of model calls. Together they found about 12 of 13.
- **Hints matter a lot.** NodeGoat is a teaching app that announces its own bugs in comments. Plain prompt on the raw repo: 11 of 13. With hints removed: 9 of 13. With all comments removed: 6 of 13. On DVNA (another teaching app, used as held-out, 18 known bugs, comments and docs removed): 12 of 18. Our automatic scorer gave too much credit in every case, so every result was checked by hand.
- **Cost shape:** the checking step takes about 45 model calls per run against 1 call for the finding step, roughly 350k–525k tokens (estimated).

## 4. What we have not shown

- No result on a repo too big for one prompt, which is where a structured pipeline should win.
- No repo newer than the model's training data, and no real-world (non-teaching) repo with known bugs.
- All labels were made by one reader (Claude), except Juice Shop, where the labels come from its maintainers' own markers. No second labeller.
- Mostly single runs and one model family. The three-run comparison of plain prompt, per-route reviewer and imported Claude or CodeQL results needs about 1,500 calls and a paid key.
- No exploit actually run in a sandbox. The tool proves a claim against the code, not against a running app.
- Honest summary: today this is a verified-findings tool, not a better finder than one prompt. Its value so far is precision (no false claims survive) and a measurement method.

## 5. Competitors and landscape

This is from our own research, mostly secondary sources, so verify before quoting.

- **XBOW:** autonomous attack agents against running apps, with non-model "validators" that confirm an exploit really worked. Strong at offensive testing. Their lesson for us: proof beats opinion.
- **OpenAI Aardvark / Codex Security, Google CodeMender and Big Sleep:** big-lab agents that read code, find or confirm issues, and in some cases propose patches. They have more compute and model access than we do.
- **Anthropic security review (Claude Code `/security-review` and its GitHub Action):** a single agent reviewing a diff or repo. Reported as not hardened against prompt injection from code comments.
- **OpenAnt (open source, Apache 2.0):** decomposition, adversarial checking and dynamic testing, with a reported cost of about $1,461 over 8 repos. We found no comparison against a plain-prompt baseline. Other open-source AI pentesters exist (Shannon, Strix).
- **CodeAnt AI:** YC-backed AI code security and review company, so YC has funded this category.
- **Classic scanners (CodeQL, Semgrep, Snyk):** rule-based, cheap and deterministic. Our eval tool can import their results to compare.
- **Research findings we rely on:** comments in a repo can steer AI reviewers (an attack called ALIBI reported over 90% success, and stripping comments was the best defence). AI cyber contests (AIxCC) rewarded stability and proof over clever technique. Benchmarks are easy to flatter, and run-to-run variance is large.

The real baseline is not "one API call". It is an agentic assistant that a developer can already run for free.

## 6. Where a pipeline could still beat a prompt (hypotheses, not proven)

1. Executable proof: run the exploit in a sandbox so a finding is confirmed, not argued.
2. Big repos: use the route map and reachability so the model sees the right code.
3. Diff and CI mode with memory, so it reviews only what changed and does not repeat itself.
4. Cost accountability: a per-run budget and a report of what each finding cost.
5. Lab or campaign mode: many repos, repeated runs, resumable, with findings tracked over time. This is the "automated security research" direction.

## 7. Startup context (YC)

Acceptance is about 1% of more than 10,000 applicants per cycle (secondary sources). YC's Summer 2026 and Fall 2026 Requests for Startups contain no security idea. The closest fits are Fall #13 "Self-Maintaining APIs" (agents read customer code and open a pull request with the fix), Summer #01 "AI-Native Service Companies" (sell the finished work, not a tool) and Fall #12 "AI-Native Compliance Infrastructure" (audit trails). Our evidence format (quoted code, line numbers, reasoning) resembles an audit trail. We have no users yet and we do not generate fixes yet. Team size is not stated here.

## 8. Known gaps before a public launch

No LICENSE, CI, Docker image, SECURITY.md or release tags. No local-model support (an OpenAI-compatible base URL). The frontend duplicates the engine in JavaScript, and its cohort percentages, 90-day timeline and revenue numbers are written by the model, not measured. No defence against comment injection yet. Planned order: run directory with cost caps, proof tiers and SARIF output, licence and CI, comment-injection hardening, sandbox proof, diff mode and GitHub Action, then lab mode.

## 9. What I want your help with

1. Given the measured results, what is the most defensible wedge: a cheaper checker, executable proof, diff review in CI, or research-lab automation?
2. How should we design a benchmark nobody can dismiss, given the leakage problem on teaching apps?
3. Who is the first paying customer, and what would they pay for?
4. How should we pitch this honestly when it ties a plain prompt today?
5. What should we cut?
