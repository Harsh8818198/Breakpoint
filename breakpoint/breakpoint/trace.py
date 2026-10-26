"""Show how one claim was checked, step by step, on one page.

A finding is only worth believing if you can see why: which files the reviewer was shown, what it quoted, whether each quote
really exists in the code as live code, what the appeal and the defender said, and, for a claim that held, who the attacker
is, where their data enters and what each of the repeated checks decided. This module prints that from a saved trace.

  python -m breakpoint.trace show RUN.json                    list the claims in an evaluation run saved with --trace
  python -m breakpoint.trace show RUN.json --index 3          print one claim's trace
  python -m breakpoint.trace check REPORT.json --codebase DIR --index 0 --save trace.json
                                                              run the strict check on one finding of a saved report and print it
  python -m breakpoint.trace show trace.json                  print it again later without any model call

The first check and the first exploitability answer are shown in full; the others as one line each (`--all` shows them in full).
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

from .exploit import EXPLOIT_LABELS, UNTRUSTED

WIDTH = 100


def _wrap(text: str, indent: int, first: str = "") -> list[str]:
    text = " ".join(str(text).split())
    if not text:
        return []
    pad = " " * indent
    return textwrap.wrap(text, WIDTH, initial_indent=first.ljust(indent) if first else pad, subsequent_indent=pad) or []


def _line(label: str, text: str) -> list[str]:
    """`label` in a 13-column gutter, then the text wrapped under it."""
    out = _wrap(text, 15, "  " + label)
    return out or ["  " + label]


def _yn(v: Any) -> str:
    return {True: "yes", False: "no"}.get(v, "unclear")


def _quote(q: dict) -> str:
    where = f"{q['file']}:{q['line']}" if q.get("line") else q.get("file", "")
    return f"{where}  {q.get('result', '')}  `{' '.join(str(q.get('quote', '')).split())[:120]}`"


def _steps(steps: list[dict]) -> list[str]:
    out: list[str] = []
    for s in steps:
        kind = s.get("step", "")
        if kind == "locate":
            out += _line("locate", "looked at " + (", ".join(s.get("files") or []) or "nothing in particular")
                         + ("; searched for " + ", ".join(s["search_terms"]) if s.get("search_terms") else "")
                         + (f". ({s['note']})" if s.get("note") else ""))
        elif kind == "read":
            files = s.get("files") or []
            out += _line("read", f"the reviewer was shown {len(files)} file(s): " + ", ".join(files[:6]) + (" ..." if len(files) > 6 else ""))
        elif kind in ("judge", "judge (second look)"):
            out += _line(kind.split(" (")[0] + (" 2" if "second" in kind else ""),
                         f"{s.get('verdict') or 'no verdict'}; impact follows: {_yn(s.get('impact_follows'))}")
            out += _wrap(s.get("reasoning", ""), 15, "               ")
            for q in s.get("quotes") or []:
                out.append(f"               quoted {q['file']}: `{q['quote'][:110]}`")
            if s.get("absent_names") and not s.get("quotes"):
                out += _wrap("says a protection is missing; names it would carry: " + ", ".join(s["absent_names"]), 15, "               ")
        elif kind == "look_again":
            out += _line("look again", "the reviewer said it could not tell and asked to see: " + ", ".join(s.get("asked_for") or ["(nothing named)"]))
        elif kind == "mechanical":
            quotes = s.get("quotes") or []
            if not quotes:
                out += _line("mechanical", "the reviewer offered no quote, so there is nothing to check")
            for i, q in enumerate(quotes):
                out += _line("mechanical" if i == 0 else "", _quote(q))
        elif kind == "absence_search":
            out += _line("absence", ("proved: " if s.get("proved") else "not proved: ") + "searched the whole repository for "
                         + ", ".join(s.get("names") or []) + ("; switched off at " + ", ".join(s["switched_off_at"]) if s.get("switched_off_at") else ""))
        elif kind == "appeal":
            out += _line("appeal", "the refutation cited " + ("; ".join(s.get("refutation_cited") or []) or "nothing") + "")
            out += _wrap(s.get("reasoning", ""), 15, "               ")
            out += _wrap("-> " + s.get("outcome", ""), 15, "               ")
            for q in s.get("quotes") or []:
                out.append("               " + _quote(q))
        elif kind == "defend":
            out += _line("defender", f"read {len(s.get('files_read') or [])} file(s); protection found: {_yn(s.get('defence_found'))}")
            out += _wrap(s.get("reasoning", ""), 15, "               ")
            for q in s.get("quotes") or []:
                out.append("               " + _quote(q))
            out += _wrap("-> " + s.get("outcome", ""), 15, "               ")
        elif kind == "decision":
            out += _line("decision", f"{s.get('status')} ({s.get('code')}): {s.get('why', '')}")
        elif kind == "error":
            out += _line("error", s.get("message", ""))
    return out


def _rules(x: dict) -> str:
    """The fixed rules an exploitability answer has to pass, and which of them it did."""
    checked = x.get("entry_checked") or {}
    marks = [("attacker is outside the trust boundary", x.get("attacker") in UNTRUSTED),
             ("no power already held", x.get("already_has_the_power") is False),
             ("path to the flaw shown", x.get("reaches_flaw") is True),
             ("entry point is live code", bool(checked) and checked.get("result") == "found, live code")]
    return "; ".join(f"{name} [{'ok' if ok else 'FAILED'}]" for name, ok in marks)


def _exploit_answer(x: dict) -> list[str]:
    out = _line("tier", f"{x.get('tier')} ({x.get('code')}): {EXPLOIT_LABELS.get(x.get('code'), '')}")
    ec = x.get("entry_checked")
    if ec:
        out += _line("entry point", _quote(ec))
    elif x.get("entry_point"):
        out += _line("entry point", f"{x['entry_point']['file']}:{x['entry_point']['line']}")
    else:
        out += _line("entry point", "none shown")
    out += _line("attacker", f"{x.get('attacker') or 'unclear'}" + (f", who chooses: {x['attacker_controls']}" if x.get("attacker_controls") else ""))
    out += _line("gains", f"reaches the flaw: {_yn(x.get('reaches_flaw'))}; already had the power: {_yn(x.get('already_has_the_power'))}")
    for label, key in (("path", "path"), ("harm", "harm"), ("only if", "condition"), ("reasoning", "reasoning")):
        if x.get(key) and str(x[key]).strip().lower() not in ("none", "null", "n/a"):      # older runs saved the word "None"
            out += _line(label, x[key])
    out += _line("rules", _rules(x))
    return out


def _result_line(entry: dict) -> str:
    outcome = entry.get("outcome", "")
    votes = entry.get("votes") or {}
    cc, ex = votes.get("code_check") or {}, votes.get("exploit") or {}
    held = f"{cc.get('confirmed', 0)} of {cc.get('cast', 0)} code checks held" if cc else ""
    exploit = f"{ex.get('yes', 0)} of {ex.get('cast', 0)} exploitability answers positive" if ex else ""
    both = ", ".join(x for x in (held, exploit) if x)
    tier = (entry.get("exploit") or {}).get("tier")
    if outcome == "kept":
        return f"FINDING ({tier or 'confirmed'}): {both}".strip().rstrip(":")
    status, _, code = outcome.partition(":")
    if status == "OBSERVATION":
        return f"NOT A FINDING: accurate about the code but not exploitable ({EXPLOIT_LABELS.get(code, code)}). {both}"
    return f"NOT KEPT ({status.lower()}: {code}). {both}"


def render(entry: dict, *, all_votes: bool = False) -> str:
    """One claim's page. `entry` has title, claim, outcome, votes, exploit and trace (a dict from the strict verifier, or the
    list of steps of a single plain check)."""
    trace = entry.get("trace") or {}
    if isinstance(trace, list):                        # a single plain check
        trace = {"code_checks": [{"status": (trace[-1] if trace else {}).get("status", ""), "steps": trace}], "exploit": []}
    bar = "=" * WIDTH
    L = [bar, *_wrap(entry.get("title", ""), 8, "CLAIM"), *_wrap(entry.get("claim", ""), 8, "")[:5],
         *_wrap(_result_line(entry), 8, "RESULT"), bar, ""]
    checks, answers = trace.get("code_checks") or [], trace.get("exploit") or []
    for i, c in enumerate(checks, 1):
        held = {"CONFIRMED": "held", "REFUTED": "refuted", "UNVERIFIED": "not proven", "ERROR": "failed"}.get(c.get("status"), str(c.get("status")).lower())
        if i == 1 or all_votes:
            L += [f"CODE CHECK {i} of {len(checks)}: {held}", *_steps(c.get("steps") or []), ""]
        else:
            L += [f"CODE CHECK {i} of {len(checks)}: {held} ({c.get('code')})", ""]
    for i, x in enumerate(answers, 1):
        if x.get("tier") is None:
            L += [f"EXPLOITABILITY {i} of {len(answers)}: no usable answer ({x.get('code')})", ""]
        elif i == 1 or all_votes:
            L += [f"EXPLOITABILITY {i} of {len(answers)}", *_exploit_answer(x), ""]
        else:
            L += [f"EXPLOITABILITY {i} of {len(answers)}: {x.get('tier')} ({x.get('code')})", ""]
    if not answers and checks and (entry.get("outcome") == "kept" or str(entry.get("outcome", "")).startswith("OBSERVATION")):
        L += ["EXPLOITABILITY: not run", ""]
    L += [bar]
    return "\n".join(line.rstrip() for line in L)


# --------------------------------------------------------------------------- loading and the command line
def load_entries(path: str) -> list[dict]:
    """Claims with a trace from an evaluation run saved with --trace, a trace saved by `check --save`, or a list of those."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "proposed" in data:
        return data["proposed"]
    if isinstance(data, dict) and "trace" in data:
        return [data]
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    raise ValueError(f"{path}: no claims with a trace (run the evaluation with --trace, or use `check --save`)")


def pick(entries: list[dict], index: int | None, title: str | None) -> dict:
    if index is not None:
        if not 0 <= index < len(entries):
            raise ValueError(f"--index {index} is out of range (0 to {len(entries) - 1})")
        return entries[index]
    if title:
        hits = [e for e in entries if title.lower() in e.get("title", "").lower()]
        if len(hits) != 1:
            raise ValueError(f"--title {title!r} matches {len(hits)} claims; use --index")
        return hits[0]
    if len(entries) == 1:
        return entries[0]
    raise ValueError("several claims: choose one with --index or --title")


def cmd_show(args) -> int:
    entries = load_entries(args.file)
    if args.index is None and not args.title and len(entries) != 1:
        for i, e in enumerate(entries):
            print(f"{i:>3}  {'trace' if e.get('trace') else 'no trace':<9} {str(e.get('outcome', '')):<34} {e.get('title', '')[:60]}")
        return 0
    entry = pick(entries, args.index, args.title)
    if not entry.get("trace"):
        raise ValueError("that claim has no trace: run the evaluation again with --trace")
    print(render(entry, all_votes=args.all))
    return 0


def cmd_check(args) -> int:
    from .blueprint import codebase_checkout
    from .codeindex import CodeIndex
    from .llm import LLMClient, LLMFatalError
    from .proof import make_verifier
    from .run import _finding_from_dict

    data = json.loads(Path(args.report).read_text(encoding="utf-8"))
    raw = data.get("findings", data) if isinstance(data, dict) else data
    entries = [{"title": d.get("title", ""), "_d": d} for d in raw]
    chosen = pick(entries, args.index, args.title)["_d"]
    f = _finding_from_dict(chosen)
    llm = LLMClient()
    print(f"Provider: {llm.provider} | Model: {llm.model}", file=sys.stderr)
    with codebase_checkout(args.codebase) as root:
        index = CodeIndex.from_dir(root)
        v = make_verifier(index, llm, checks=args.checks, exploit=not args.no_exploit, trace=True)
        try:
            r = v([f])[0]
        except LLMFatalError as e:
            sys.exit(f"[error] {e}")
    entry = {"title": f.title, "claim": f.description[:600], "impact": f.impact[:300],
             "outcome": "kept" if r["status"] == "CONFIRMED" else f"{r['status']}:{r['code']}",
             "votes": r.get("votes") or {}, "exploit": r.get("exploit") or {}, "evidence": r["evidence_items"], "trace": r["trace"]}
    print(render(entry, all_votes=args.all))
    if args.save:
        Path(args.save).write_text(json.dumps(entry, indent=2), encoding="utf-8")
        print(f"[+] Saved the trace to {args.save}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m breakpoint.trace", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("show", help="print a saved trace (no model calls)")
    sp.add_argument("file", help="an evaluation run saved with --trace, or a trace saved by `check --save`")
    sp.add_argument("--index", type=int, help="position of the claim in the run (list them by leaving this out)")
    sp.add_argument("--title", help="part of the claim's title")
    sp.add_argument("--all", action="store_true", help="show every check and every exploitability answer in full")
    sp.set_defaults(fn=cmd_show)
    sp = sub.add_parser("check", help="run the strict check on one finding of a saved report and print its trace")
    sp.add_argument("report", help="a JSON report with findings (from --output *.json, --baseline, --route-review)")
    sp.add_argument("--codebase", required=True, help="the folder or git URL the report is about")
    sp.add_argument("--index", type=int)
    sp.add_argument("--title")
    sp.add_argument("--checks", type=int, default=3)
    sp.add_argument("--no-exploit", action="store_true")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--save", metavar="OUT.json", help="save the trace so `show` can print it again")
    sp.set_defaults(fn=cmd_check)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, OSError) as e:
        sys.exit(f"[error] {e}")


if __name__ == "__main__":
    raise SystemExit(main())
