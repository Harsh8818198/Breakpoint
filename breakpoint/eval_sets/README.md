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

## What is still missing

- **Post-cutoff repositories.** A bug published after a model's training cutoff cannot have been memorised. Add at least two
  small, recently patched projects, labelled from the fix commit.
- **Repositories too big for one prompt** that are not teaching apps.
- **Other languages and frameworks.** Every set here is Express.
- **Second labellers** for all three sets.
