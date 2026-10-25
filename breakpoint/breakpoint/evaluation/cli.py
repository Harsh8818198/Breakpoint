"""breakpoint-eval: compare ways of finding bugs on repositories whose bugs are known.

  breakpoint-eval list
  breakpoint-eval info nodegoat --variant hints               size, routes, does it fit one prompt, call budget
  breakpoint-eval fetch dvna                                  clone the pinned commit (the code is read, never run)
  breakpoint-eval run dvna --arm plain --arm route-review --runs 3
  breakpoint-eval run dvna --arm import:claude-review.json    compare a result produced elsewhere (JSON or SARIF)
  breakpoint-eval adjudicate --set dvna                       write the issues a person must judge
  breakpoint-eval report --set dvna                           the comparison, with every caveat that applies

Sets made from public security advisories (the code just before the maintainers' fix, labelled by the fix):
  breakpoint-eval harvest --count 8 --seed 1                  choose and build sets in a fixed order, logging every skip
  breakpoint-eval advisory GHSA-xxxx-xxxx-xxxx                build the set for one advisory
  breakpoint-eval history --arm plain                         one table over all of them
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..llm import LLMFatalError
from . import advisory, score
from . import history as history_mod
from .runner import run_dir, run_eval
from .sets import SETS_DIR, describe, fetch, list_sets, load_set, validate_labels

DEFAULT_OUT = "eval_runs"
DEFAULT_CACHE = ".breakpoint/eval-cache"
DEFAULT_HISTORY = str(SETS_DIR / "history")


def _paths(args) -> tuple[Path, Path]:
    return Path(args.out), Path(args.cache)


def cmd_list(args) -> int:
    for sid in list_sets():
        es = load_set(sid)
        print(f"{sid:<12} {es.role:<8} {len(es.bugs):>3} bugs  variants: raw{''.join(', ' + v for v in es.variants)}   {es.title}")
    n = len(history_mod.history_sets())
    if n:
        print(f"history      heldout  {n:>3} advisory sets in eval_sets/history (one known flaw each; run one with `run history/<id>`)")
    return 0


def cmd_info(args) -> int:
    out, cache = _paths(args)
    d = describe(load_set(args.set), args.variant, cache)
    print(json.dumps(d, indent=2))
    return 0


def cmd_fetch(args) -> int:
    out, cache = _paths(args)
    p = fetch(load_set(args.set), cache)
    print(f"{args.set}: pinned checkout at {p}")
    return 0


def cmd_check(args) -> int:
    out, cache = _paths(args)
    es = load_set(args.set)
    bad = []
    for v in ["raw", *es.variants]:
        problems = validate_labels(es, v, cache)
        bad += [f"[{v}] {p}" for p in problems]
        print(f"{es.id} [{v}]: {len(es.bugs) - len(problems)} of {len(es.bugs)} known bugs have live code at their labelled lines")
    for p in bad:
        print("  PROBLEM " + p)
    return 1 if bad else 0


def cmd_snippets(args) -> int:
    from .snippets import labels_from_snippets
    bugs = labels_from_snippets(args.root, args.challenges)
    print(json.dumps(bugs, indent=2))
    print(f"# {len(bugs)} bugs", file=sys.stderr)
    return 0


def cmd_run(args) -> int:
    out, cache = _paths(args)
    es = load_set(args.set)
    try:
        run_eval(es, args.variant, args.arm or ["plain"], args.runs, out, cache, verify=not args.no_verify,
                 opts={"max_calls": args.max_calls}, resume=not args.fresh)
    except LLMFatalError as e:
        print(f"\n[error] {e}\nRuns that finished are saved in {run_dir(out, es, args.variant)}; run the same command again to continue.")
        return 2
    print(f"\nNext: breakpoint-eval adjudicate --set {es.id} --variant {args.variant}   then   breakpoint-eval report --set {es.id} --variant {args.variant}")
    return 0


def _adj_path(args, es) -> Path:
    return Path(args.adjudication) if args.adjudication else run_dir(Path(args.out), es, args.variant) / "adjudication.json"


def cmd_adjudicate(args) -> int:
    es = load_set(args.set)
    runs = score.load_runs(Path(args.out), es.id, args.variant)
    if not runs:
        print("No runs found. Run `breakpoint-eval run` first.")
        return 1
    target = _adj_path(args, es)
    todo = score.adjudication_todo(es, args.variant, runs, score.load_adjudication(target))
    todo_path = target.with_name("adjudication-todo.json")
    todo_path.parent.mkdir(parents=True, exist_ok=True)
    todo_path.write_text(json.dumps(todo, indent=2), encoding="utf-8")
    left = sum(1 for c in todo["clusters"] if not c["verdict"])
    print(f"{len(todo['clusters'])} issues, {left} without a verdict. Edit {todo_path}, then save it as {target.name} "
          f"(or pass it with --adjudication).")
    return 0


def cmd_report(args) -> int:
    es = load_set(args.set)
    out = Path(args.out)
    runs = score.load_runs(out, es.id, args.variant)
    if not runs:
        print("No runs found. Run `breakpoint-eval run` first.")
        return 1
    adj = _adj_path(args, es)
    summary = score.summarize(es, args.variant, runs, score.load_adjudication(adj))
    text = score.render(summary)
    print(text)
    d = run_dir(out, es, args.variant)
    (d / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (d / "summary.md").write_text(text + "\n", encoding="utf-8")
    return 0


def cmd_advisory(args) -> int:
    try:
        data = advisory.build_set(advisory.get_advisory(args.ghsa), fixed_since=args.since, max_source_bytes=args.max_source_kb * 1000)
    except advisory.Skip as e:
        print(f"{args.ghsa}: not usable ({e})")
        return 1
    target = Path(args.sets_dir) / data["id"] / "set.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    b = data["bugs"][0]
    print(f"{target}\n  {data['title']}\n  {b['class']} {b['cwe']}; label: " + ", ".join(f"{l['file']}:{l['lines'][0]}-{l['lines'][1]}" for l in b["locations"]))
    return 0


def cmd_harvest(args) -> int:
    rec = advisory.harvest(args.ecosystem or ["npm", "pip"], args.since, args.count, args.seed, Path(args.sets_dir),
                           max_considered=args.max_considered, max_source_bytes=args.max_source_kb * 1000)
    print(f"\n{len(rec['kept'])} sets built; {len(rec['considered'])} advisories considered. The full record is {Path(args.sets_dir) / 'selection.json'}")
    return 0 if rec["kept"] else 1


def cmd_history(args) -> int:
    sets = history_mod.history_sets(Path(args.sets_dir))
    if not sets:
        print(f"No advisory sets in {args.sets_dir}. Run `breakpoint-eval harvest` first.")
        return 1
    summary = history_mod.summarize_history(sets, Path(args.out), args.variant, args.arm)
    text = history_mod.render(summary, sets)
    print(text)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"history_{args.arm}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / f"history_{args.arm}.md").write_text(text + "\n", encoding="utf-8")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="breakpoint-eval", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, set_required=True):
        sp.add_argument("set", nargs=None if set_required else "?", help="set id under eval_sets/, or a path to a set.json")
        sp.add_argument("--variant", default="raw", help="raw (as published) or a cleaned variant defined by the set")
        sp.add_argument("--out", default=DEFAULT_OUT, help=f"where runs are saved (default {DEFAULT_OUT})")
        sp.add_argument("--cache", default=DEFAULT_CACHE, help=f"where repositories are cloned (default {DEFAULT_CACHE})")

    sub.add_parser("list", help="the evaluation sets in eval_sets/").set_defaults(fn=cmd_list)
    sp = sub.add_parser("info", help="size, routes, whether the source fits one prompt, rough call budget")
    common(sp)
    sp.set_defaults(fn=cmd_info)
    sp = sub.add_parser("fetch", help="clone the pinned commit")
    common(sp)
    sp.set_defaults(fn=cmd_fetch)
    sp = sub.add_parser("check", help="verify every known bug still has live code at its lines in every variant")
    common(sp)
    sp.set_defaults(fn=cmd_check)
    sp = sub.add_parser("snippets", help="print labels read from vuln-code-snippet markers (Juice Shop) in a pristine checkout")
    sp.add_argument("root")
    sp.add_argument("--challenges", help="path to challenges.yml, for readable titles")
    sp.set_defaults(fn=cmd_snippets)
    sp = sub.add_parser("run", help="run arms on a set, several times each")
    common(sp)
    sp.add_argument("--arm", action="append", help="plain | route-review | import:<file>; repeat for several (default plain)")
    sp.add_argument("--runs", type=int, default=3, help="runs per arm (default 3; one run is not a measurement)")
    sp.add_argument("--no-verify", action="store_true", help="skip the code check (kept findings are then unproven claims)")
    sp.add_argument("--max-calls", type=int, default=150, help="cap on route-review calls per run")
    sp.add_argument("--fresh", action="store_true", help="redo runs even if their files exist")
    sp.set_defaults(fn=cmd_run)
    def advisory_opts(sp):
        sp.add_argument("--sets-dir", default=DEFAULT_HISTORY, help="where advisory sets are written (default eval_sets/history)")
        sp.add_argument("--since", default=advisory.DEFAULT_SINCE,
                        help=f"advisory published and fix committed on or after this day (default {advisory.DEFAULT_SINCE}, a week after the model's release)")
        sp.add_argument("--max-source-kb", type=int, default=advisory.MAX_SOURCE_BYTES // 1000,
                        help="skip repositories whose source would not fit the plain prompt (default %(default)s KB)")

    sp = sub.add_parser("advisory", help="build the evaluation set for one GitHub security advisory with a fix commit")
    sp.add_argument("ghsa", help="advisory id, such as GHSA-xxxx-xxxx-xxxx")
    advisory_opts(sp)
    sp.set_defaults(fn=cmd_advisory)
    sp = sub.add_parser("harvest", help="build several advisory sets, chosen in a fixed pseudo-random order, logging every skip")
    sp.add_argument("--ecosystem", action="append", help="npm, pip, go, maven, composer, rubygems... (repeat; default npm and pip)")
    sp.add_argument("--count", type=int, default=8, help="how many sets to build (default %(default)s)")
    sp.add_argument("--seed", default="breakpoint-history-1", help="the walk order is sha1(seed|id): change it only to start a new sample")
    sp.add_argument("--max-considered", type=int, default=120, help="stop after looking at this many advisories")
    advisory_opts(sp)
    sp.set_defaults(fn=cmd_harvest)
    sp = sub.add_parser("history", help="one table over all advisory sets: proposed, kept, what else was kept")
    sp.add_argument("--arm", default="plain")
    sp.add_argument("--variant", default="raw")
    sp.add_argument("--sets-dir", default=DEFAULT_HISTORY)
    sp.add_argument("--out", default=DEFAULT_OUT)
    sp.set_defaults(fn=cmd_history)
    for name, fn, helptext in (("adjudicate", cmd_adjudicate, "write the issues a person must judge"),
                               ("report", cmd_report, "the comparison and its caveats")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--set", dest="set", required=True)
        sp.add_argument("--variant", default="raw")
        sp.add_argument("--out", default=DEFAULT_OUT)
        sp.add_argument("--adjudication", help="verdicts file (default <out>/<set>__<variant>/adjudication.json)")
        sp.set_defaults(fn=fn)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if getattr(args, "runs", 1) < 1:
        sys.exit("--runs must be at least 1")
    try:
        return args.fn(args)
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as e:
        sys.exit(f"[error] {e}")


if __name__ == "__main__":
    raise SystemExit(main())
