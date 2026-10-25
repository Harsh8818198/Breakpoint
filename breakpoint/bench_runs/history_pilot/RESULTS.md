# Advisory sets, first measurement (2026-10-24 and 25)

Real, recently fixed vulnerabilities, labelled by the maintainers, fixed after the model existed. What a plain prompt finds
there, and what the code check does with it. Method and caveats are in `eval_sets/README.md` ("Advisory sets").

## Setup

- **Sets.** `eval_sets/history/`: 22 advisories, one known flaw each, small JavaScript and Python libraries. The harvest walked
  519 of 1,732 reviewed high/critical npm and PyPI advisories (published since 2026-03-10) in a fixed order, seed
  `breakpoint-history-1`, and built 24. The rest were skipped by mechanical filters, all recorded in `selection.json`:
  198 had no usable fix-commit link, 120 had source too large for one prompt, 61 had several fix commits, 50 changed too many
  files, 34 were large fixes, 14 changed no source, 14 were merge commits, 3 fixed another repository, 1 had no GitHub location.
- **Label review.** Before any model ran, the fix patch of every set was read against its advisory text. Two of the 24 were
  dropped: `ghsa-rp9m-7r4c-75qg` (the advisory says the library has no flaw; the fix only adds a warning) and
  `ghsa-r6x4-923q-g947` (the pinned code no longer contains the flaw the advisory describes). One reader.
- **Model.** `gemini/gemini-3.1-flash-lite` (released 2026-03-03, knowledge cutoff January 2025). Every fix was committed after the
  release, so this model cannot have trained on it.
- **Finder.** The plain prompt: all the source that fits, asked once for 15 vulnerabilities. Three runs per set, no code check:
  66 runs, 66 calls (`breakpoint-eval run history/<id> --arm plain --runs 3 --no-verify --out finder`).
- **Reading.** I read every candidate against the advisory and the fix, per run, and recorded Y (a candidate describes the
  advisory's flaw), P (right place and class, but a different or vaguer mechanism, or only a hedge) or N, in
  `finder/proposed_read.json`. This was written before the code check ran on anything.

## What the plain finder found

| | runs (of 66) | sets (of 22) with it in at least one run |
|---|---|---|
| A candidate describes the advisory's flaw (Y) | 6 (9%) | 4 |
| Y, or right place and class but vaguer (Y or P) | 23 (35%) | 12 |
| A candidate's lines fall in the fix's lines (mechanical) | 16 (24%) | 9 |

The mechanical match is wrong both ways: it credited coincidences (a find-my-way "memory limit on route storage" claim,
a devalue claim about globalThis lookups) and missed all three correct scim-patch findings because they cited the
`assign` function while the fix was in `resolvePaths`. Full table: `finder/history_plain.md`.

For comparison, the same plain prompt on the teaching apps (`bench_runs/eval_pilot/`): NodeGoat 11 of 13 known bugs on the raw
repository, 6 of 13 with every comment removed; DVNA 12 of 18. On real, unseen flaws it named the maintainers' flaw clearly in
about one run in eleven.

## What the code check did

- **On the candidates read as Y or P (26 candidates, `check/`).** It kept 6 of the 7 Y candidates (the seventh came back
  unverified: "quotes are comments, not live code") and 0 of the 19 P candidates.
- **Repeated on the 9 candidates of the four sets that had a Y (`check_repeat/`).** The keep/drop decision was the same 7
  times and different 2 times. Of the 7 Y candidates, 4 were kept in both runs, and 3 flipped or stayed dropped:
  the i18next-fs-backend one, kept the first time, was refuted the second ("a protection enforced in the code defeats the
  claim": it pointed at the key filter in a neighbouring function); one adm-zip candidate flipped the same way; the
  @fastify/static one was dropped both times (unverified, then "contradicted by code"). Details: `check_outcomes.json`.
- **On everything the finder said (four sets, run 1, all 15 candidates each, 60 candidates, about 45 calls per set).** 10 kept, 43
  refuted, 7 unverified. I read the 10 survivors against the code (`survivors_read.json`): none is a vulnerability. Six
  are accurate observations about a feature or a local tool ("`eval` is used to load .js translation files", "stdin is read without
  a size limit"), four are wrong (a speculative homograph claim, a user-controlled `import()` path that is the application's
  own option, a property read called prototype pollution, `rm -fr` called a temporary-file race). In this run the check also
  refuted the one flaw-describing candidate in these four lists (i18next-fs-backend).

## What it means

1. **On real, unseen code a plain prompt rarely names the flaw.** About 9% of runs strictly, 35% leniently, 4 of 22 sets. The
   teaching-app numbers (6 to 11 of 13) were not a guide to this.
2. **The code check is a strong noise filter.** It removed 83% of 60 claims and all 19 vague ones, and it kept most clear
   hits.
3. **Kept does not mean vulnerable.** The check proves a claim about what the code does. It does not decide whether that is a
   vulnerability: none of 10 survivors was one. Without a judgement of attacker-controlled input and impact, "verified
   findings" means "accurate observations", which is not what a user wants.
4. **The check is not stable.** Decisions flipped on 2 of 9 repeated candidates, including a true flaw. One check run per
   claim is not enough; a result needs several, and the report should say how often a finding survived.

## Limits

One model (and the same model is the finder and the checker). 22 flaws in small libraries; the sets exclude repositories too big
for one prompt, on purpose. Labels come from the maintainers' fixes but the check that each fix matches its advisory, every
reading above, and every survivor verdict are by one reader (Claude), not independently reviewed. P is a judgement call. Three
finder runs per set; the code check was run once on most candidates and twice on 9; the all-candidates run covers only 4 sets.
The free tier limited how much could be run. No prompt, retrieval rule or verifier setting was changed after seeing these results; the
only changes made along the way were to how the model's reply is read (a regex with a backslash, or a raw line break, inside a JSON
string made 9 of the first 66 finder runs unreadable; they were redone, not counted as misses) and to retrying a dropped connection.
