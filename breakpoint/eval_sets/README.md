# Evaluation sets

A set is a repository pinned to a commit plus the bugs known to be in it. `breakpoint-eval` runs ways of finding bugs
(one plain prompt, the per-route review, results imported from other tools) on a set and reports what they found and
what it cost. See the main README, "Evaluation harness".

| Set | Role | Bugs | Where the labels come from | Language |
|---|---|---|---|---|
| `nodegoat` | **dev**: we built and tuned Breakpoint against it | 13 | Claude, from the source and the project's tutorial; one reader | JavaScript, Express |
| `dvna` | held out | 18 | The project's own documented list (`docs/solution`) mapped to source lines by Claude; one reader | JavaScript, Express |
| `juice-shop` | held out, larger | 15 | The maintainers' own `vuln-code-snippet` markers in the server-side source (independent of us) | TypeScript, Express |

All three are public teaching apps that models have very likely seen, and that announce their own bugs. Treat them as a
harness check and a leak measurement, not as proof of anything on real code. See "What is still missing" below.

## Variants: removing the answer key

Intentionally vulnerable apps carry their own answers: comments such as `Fix for A8 - CSRF`, tutorial pages, solution
write-ups, challenge hooks, and in Juice Shop's case `vuln-code-snippet` markers on the vulnerable lines. A model that reads
them is not finding anything. Every set therefore has cleaned *variants*: copies of the checkout with those leaks removed
and **every line keeping its number**, so the labels stay valid.

| Operation (in `set.json`, under `variants`) | What it does |
|---|---|
| `drop_paths` | files removed (README, docs, tutorial pages, solution files) |
| `blank_comment_lines_matching` | whole comment lines whose text matches a pattern lose their text |
| `blank_all_comments` | every whole-line comment loses its text |
| `blank_lines_matching` | any matching line is emptied (comment lines keep their delimiters) |
| `strip_regex` | text removed inside a line, such as a trailing marker |

A comment stays a comment: emptying `/* Fix for A7` must not turn the commented-out code under it into live code, so the
delimiters are kept. Run `breakpoint-eval check <set>` after editing a recipe: it fails if any known bug has no live code
left at its lines in any variant.

Run the same arm on `raw` and on a cleaned variant to measure what the leak is worth.

## Adding a set

1. Create `eval_sets/<id>/set.json`:

```json
{
  "id": "myapp", "title": "My App", "role": "heldout",
  "repo": {"url": "https://github.com/owner/repo", "commit": "<full sha>"},
  "language": "python", "framework": "flask",
  "provenance": "who labelled the bugs, from what, and whether a second person checked",
  "contamination": "how public the repo is, and whether models may have seen it or its fix",
  "bugs": [
    {"id": "sqli-login", "title": "SQL injection in login", "class": "injection", "cwe": "CWE-89",
     "locations": [{"file": "app/auth.py", "lines": [41, 44]}]}
  ],
  "variants": {"clean": {"drop_paths": ["docs/*"]}}
}
```

   `repo` may instead be `{"path": "/local/dir"}`, and may carry `"sparse": [...]` (sparse-checkout patterns) for
   repositories with file names Windows cannot hold.
2. Every `locations` entry is where a correct finding could point; a missing protection can be labelled where it should be.
3. `breakpoint-eval check myapp` then `breakpoint-eval info myapp`.

## Labelling rules

- Label from the patch or the documentation, not from what a model reported.
- Keep labels out of every prompt, retrieval rule and verifier tuning. Never tune on a held-out set.
- Prefer repositories whose bug is announced nowhere in the code. Where that is impossible, clean it and say so.
- One reader is not enough for a number you will quote: have a second person check the labels and the adjudication.
- Record `provenance` honestly, including "one reader, not reviewed".

## Advisory sets: real fixes made after the model existed (`eval_sets/history/`)

The sets above are teaching apps labelled by us. The advisory sets are the opposite: real projects, labelled by their
maintainers, and fixed after the model was released.

A GitHub security advisory that links its fix commit gives everything a set needs without a human labeller: the parent of
the fix commit is the vulnerable code, the lines the fix changed are where the flaw was, and the advisory text says what
the flaw is. Choosing only advisories published, and fixes committed, on or after 2026-03-10 (a week after
`gemini-3.1-flash-lite-preview` launched; its knowledge cutoff is January 2025) means that model cannot have trained on them.
A model with a later cutoff might have: the contamination note in each set says so.

```bash
breakpoint-eval harvest --count 24 --seed breakpoint-history-1    # choose and build sets; writes eval_sets/history/selection.json
breakpoint-eval advisory GHSA-xxxx-xxxx-xxxx                      # one advisory
breakpoint-eval run history/ghsa-xxxx-xxxx-xxxx --arm plain --runs 1
breakpoint-eval history --arm plain                               # one table over every set that has runs
```

How the sets are chosen, so nobody can say we picked the easy ones:

- Reviewed advisories of severity high or critical, in npm and PyPI, published since the cut-off date, taken in a fixed
  pseudo-random order (`sha1(seed|id)`), never by how promising they look.
- Mechanical filters only, applied from GitHub's data before any model sees code: exactly one fix commit in the advisory's
  own repository, committed after the cut-off, with one parent; the fix changes 1 to 4 source files and at most 80 lines
  (tests, docs, lockfiles and vendored code do not count); it removes or changes at least one old line, or adds a check
  (then the label is the line before the insertion); the repository's source fits the plain prompt (250 KB).
- Every advisory that was considered, and why each skipped one was skipped, is in `selection.json`. In the first
  harvest, 519 were considered and 24 built; most of the rest had no usable fix-commit link (198), source too large (120) or
  several fix commits (61).
- `history.label_review` records whether a person read the patch against the advisory text. It starts as `not reviewed`. In the first
  harvest every fix patch was read before any model ran: 22 matched their advisory, 2 were dropped (listed in `selection.json`).

First results (22 sets, plain prompt, gemini-3.1-flash-lite): `bench_runs/history_pilot/RESULTS.md`. In short: the prompt named
the maintainers' flaw clearly in 6 of 66 runs, and the code check kept most clear hits but kept no vulnerability among 10
survivors on four sets.

What this does and does not show:

- Each set holds **one** flaw, so one set is a yes or no. Only the total over many sets means anything.
- A fix commit labels the flaw it fixed. It cannot say whether any *other* finding is false, so precision on everything else
  still needs a person to read the findings.
- Sets are limited to repositories small enough for one prompt, on purpose: that is the fair test for the plain-prompt arm.
  It says nothing about repositories too big for one prompt, which is where a structured pipeline should have an advantage.
- The vulnerable code can still resemble earlier public fixes of similar bugs in the same project.

## What is still missing

- **Repositories too big for one prompt** that are not teaching apps (the advisory sets are small on purpose).
- **Other languages and frameworks.** Every set here is Express.
- **Second labellers** for all three sets.
