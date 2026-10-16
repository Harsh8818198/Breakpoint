"""Does the route map put each known bug's code inside some route's node? (no model calls, no key needed)

    python -m tests.eval_routemap --codebase path/to/NodeGoat

For each of the 13 real NodeGoat bugs, checks whether the lines where the bug lives overlap the code of at least one
route node (its registration, the protections in front of it, its handler, or what the handler calls). Bugs in app-wide
setup (session settings, template engine, CSRF) belong to no single route; those should land in the app-level code.
This measures the map alone. It says nothing about whether a reviewer then finds the bug.
"""

from __future__ import annotations

import argparse
import json
import os

from breakpoint.codeindex import CodeIndex
from breakpoint.routemap import map_routes

HERE = os.path.dirname(__file__)


def _overlaps(span, path: str, lo: int, hi: int) -> bool:
    return span.file == path and span.start <= hi and lo <= span.end


def locate(bug: dict, rm, index: CodeIndex) -> tuple[list[str], list[str]]:
    """(route labels whose node covers the bug, app-level names that cover it)."""
    routes, app = [], []
    for loc in bug["locations"]:
        path = index.resolve_path(loc["file"])
        if not path:
            continue
        lo, hi = loc["lines"]
        for r in rm.routes:
            if any(_overlaps(s, path, lo, hi) for s in r.spans()) and r.label not in routes:
                routes.append(r.label)
        for s in rm.app_level:
            if _overlaps(s, path, lo, hi) and s.file not in app:
                app.append(s.file)
    return routes, app


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codebase", required=True)
    ap.add_argument("--gold", default=os.path.join(HERE, "fixtures", "nodegoat_gold_locations.json"))
    args = ap.parse_args(argv)

    index = CodeIndex.from_dir(args.codebase)
    rm = map_routes(index)
    gold = json.load(open(args.gold, encoding="utf-8"))["bugs"]
    print(f"{len(index)} files indexed; {len(rm.routes)} routes found; entry {rm.entry_file}; "
          f"{len(rm.global_middleware)} app-level middleware lines, {sum(not g['active'] for g in rm.global_middleware)} switched off")
    in_route = app_only = neither = 0
    for bug in gold:
        routes, app = locate(bug, rm, index)
        if routes:
            in_route += 1
            tag, where = "route", ", ".join(routes[:4]) + (" ..." if len(routes) > 4 else "")
        elif app:
            app_only += 1
            tag, where = "app", ", ".join(app)
        else:
            neither += 1
            tag, where = "MISSED", ""
        print(f"[{tag:<6}] {bug['title']}" + (f"   <- {where}" if where else ""))
    print(f"\nin a route's node: {in_route}/{len(gold)} | only in app-level code: {app_only} | in neither: {neither}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
