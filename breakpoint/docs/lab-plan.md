# The Breakpoint lab: plan

Written 2026-10-25. Builds on `architecture-study.md` (section 5.13, lab mode) and the measurements in
`bench_runs/history_pilot/RESULTS.md`.

## What the lab is

A place where security claims come in, get checked, get a human verdict when the machine is unsure, and leave as a
proven finding or a recorded dismissal. Every claim, every check and every verdict is kept, so the lab can say how
good its own checking is, and that number is the product.

A claim can come from anywhere: Breakpoint's own finder, another tool's JSON or SARIF, a bug-bounty submission, or a
person. The lab does not care who found it. It decides whether the claim is real and exploitable, and shows why.

## The unit: a case

One **case** is one claim about one commit of one repository: a title, the lines it points at, the description, who
made it. Same claim at a later commit is a new case linked to the first. Everything below hangs off a case.

## What the lab stores

One SQLite file (`.breakpoint/lab.db`), standard library only, nothing to install. Rows are only added, never
overwritten, so a flip-flop between two checks stays visible. (Earlier measurements showed the checker changing its mind
on 2 of 9 claims; the lab must not hide that.)

| Table | One row is | Key fields |
|---|---|---|
| `targets` | a repository at a commit | url, commit, languages, lines, fits-in-one-prompt |
| `sources` | a finder | name (own finder, a named tool, human), version, kind |
| `cases` | one claim | target, source, fingerprint, title, file, line, bug class (CWE), the claim as received, first seen |
| `checks` | one run of the checker on a case | time, models per stage, prompt hash, number of votes and how many agreed, verdict, reason, exploitability tier, calls, tokens, cost |
| `evidence` | a line the checker relied on | check, file, line, quote |
| `proofs` | an executable proof | case, script, sandbox image digest, result, reproduced N of M times |
| `verdicts` | a person's decision | case, real / not real / not a vulnerability, reason, who, when |
| `gold` | a known real flaw | target, advisory id, fix lines (from the evaluation sets) |
| `campaigns` | a batch job | targets, sources, budget, spent, status |

Two rules:
- **`fingerprint`** is bug class + file + enclosing function + normalised vulnerable line, not the line number, so
  the same claim from two tools, or from two commits, is recognised as one case.
- **`verdicts` and `gold` are the labels.** Every human decision becomes a labelled example. The lab's accuracy numbers
  are computed from them, not from anyone's opinion of the tool.

## The queue

Each case is in exactly one state.

```
new -> checking -> refuted            (machine closes it)
                -> observation        (true of the code, not a vulnerability; machine closes it)
                -> confirmed          (true and exploitable by the checker's judgement)
                -> needs-human        (votes split, models disagree, or the claim is high severity)
confirmed / needs-human -> real | not-real   (a person)
real -> proved                        (an exploit ran in the sandbox)
real / proved -> reported -> fixed | dismissed
```

Routing rules that follow from what we measured:

1. **A unanimous refusal is not safe to trust blindly.** Two true flaws (i18next-fs-backend, send) were refuted by
   all three votes. So: a random 10% of machine-closed cases go to a person as an audit, and any refuted case from a
   source we trust is re-checked with a second model family before it closes.
2. **Split votes always go to a person.** That is where the checker is least sure.
3. **Confirmed cases of high severity go to a person before anything is reported.** The lab never sends a report
   on its own.
4. **People see the evidence first, the verdict second**: quoted lines, the entry point, the path, and the checker's
   reason. The person decides in under a minute or the evidence is not good enough.

## The numbers the lab prints

These are what you show YC. Every one is computed from the tables above.

- Claims in, and the share closed by the machine without a person.
- **Agreement between the checker and the people**, on the cases a person judged. This is the accuracy figure.
- Of the real flaws in `gold`, how many the checker kept (recall), and of what it kept, how many were real (precision).
- Cost per confirmed real finding, and per claim checked.
- How often the checker changed its mind on the same case (stability).

## Build order

Each step ends with something you can check. Sizes: S = a day or two, M = about a week, L = longer.

| # | Step | Size | Done when |
|---|---|---|---|
| 0 | **Make the checker worth putting in a lab.** Run the strict check on all candidates of the four sets that have a real flaw and read the survivors. Add a second model family as defender and see whether it rescues the two dropped flaws. | M | Survivors read by hand; a number for "real flaw kept" and "survivor is a vulnerability" on the 22 advisory sets, three runs |
| 1 | **Store and intake.** `breakpoint lab add file.json/sarif`, the SQLite schema, fingerprints, dedupe. Load the existing history candidates and `bench_runs` as the first data. | M | Importing the same file twice adds nothing; the 22 advisory sets load with their `gold` rows |
| 2 | **Check runner.** `breakpoint lab check`: runs the strict check on `new` cases, writes one `checks` row each, resumes after a crash, stops at `--max-cost`. | M | Kill it mid-run and restart: no lost work, no repeated work; cost per case is printed |
| 3 | **Queue and review.** `breakpoint lab queue` and `breakpoint lab review <case>`; routing rules above; the audit sample; the stats page (text first, one static HTML file later). | M | You review 30 cases in one sitting; the agreement figure appears and updates |
| 4 | **Campaigns.** A file listing targets, sources and a budget; run it unattended; a diff of what is new since last time. | M | A run over 10 repositories finishes or stops cleanly at budget and reports only what is new |
| 5 | **Proof.** Sandbox and executable proof for a few bug classes, stored in `proofs` with a bundle that re-runs with one command. Needs its own plan (sandbox design, bug classes, safety). | L | At least half the confirmed cases in the supported classes reproduce, none of them later judged false |
| 6 | **Disclosure record and sharing.** Who was told, when, embargo, fix commit; several people using one lab. | M | Only built if people other than you use the lab |

Steps 1 to 3 are the lab in its first useful form: about three weeks of work. Step 0 comes first on purpose. A lab
multiplies whatever the checker gets right and wrong, and today it drops half of the real flaws we tried.

## What we are not building

- Our own finder as the headline. It stays as one source among others.
- Personas, generations, evolution (already set aside in the architecture study).
- A web app before step 3 has real use. The frontend question stays parked.
- Automatic reporting or disclosure. The lab prepares evidence; a person sends it.

## Decisions for you

1. **Who is the reviewer** in the first months? It is you, which means the "agreement with people" number is agreement
   with one person. Get a second reviewer early (one of the people Boardy finds is a good fit).
2. **Which tools' output to import first.** My suggestion: Claude's security review, a CodeQL or Semgrep run, and
   Breakpoint's own plain prompt. Three sources are enough to show the lab does not depend on its own finder.
3. **Whether the lab stays local** (SQLite on your machine) until a second user exists. My suggestion: yes.
