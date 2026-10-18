"""Evaluation sets: a repository pinned to a commit, the bugs known to be in it, and the ways its leaks can be removed.

A set lives in `eval_sets/<id>/set.json`. The repository is cloned once into a cache directory and never executed.
Every set can have *variants*, which are copies of the checkout with leaks removed while every line keeps its number,
so the known-bug locations stay valid:

  raw         the repository exactly as published
  <name>      `drop_paths` (files removed), `blank_all_comments`, `blank_comment_lines_matching` (whole comment lines
              blanked when they match), `blank_lines_matching` (any line blanked), `strip_regex` (text removed inside a
              line, such as a trailing `// vuln-code-snippet` marker)

Why variants exist: intentionally vulnerable apps announce their own bugs ("Fix for A8 - CSRF", a tutorial page, a list
of challenge solutions). A model that reads those is not finding anything. Running the same arm on `raw` and on a cleaned
variant measures how much the leak is worth.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..codeindex import IGNORE_DIRS, CodeIndex, comment_mask, is_secret_file

SETS_DIR = Path(__file__).resolve().parent.parent.parent / "eval_sets"
_TEXT_EXTS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".py", ".rb", ".java", ".go", ".php", ".cs", ".html", ".htm",
              ".ejs", ".njk", ".vue", ".yml", ".yaml", ".json", ".md", ".txt", ".css", ".scss", ".sql", ".sh", ".xml"}


@dataclass
class Bug:
    id: str
    title: str
    locations: list[dict]                    # [{"file": "app/routes/x.js", "lines": [31, 34]}]
    cls: str = ""
    cwe: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "class": self.cls, "cwe": self.cwe, "locations": self.locations,
                "notes": self.notes}


@dataclass
class EvalSet:
    id: str
    title: str
    role: str                                # "dev" (we tuned on it) or "heldout"
    repo: dict                               # {"url", "commit"} or {"path"}
    bugs: list[Bug]
    language: str = ""
    framework: str = ""
    provenance: str = ""                     # who labelled the bugs and how
    contamination: str = ""                  # how public the repo is, whether models may have seen it
    variants: dict = field(default_factory=dict)
    path: Path | None = None

    def bug(self, bug_id: str) -> Bug | None:
        return next((b for b in self.bugs if b.id == bug_id), None)

    def variant(self, name: str) -> dict:
        if name == "raw":
            return {}
        if name not in self.variants:
            raise KeyError(f"set {self.id!r} has no variant {name!r} (has: raw, {', '.join(self.variants) or 'none'})")
        return self.variants[name]


def load_set(ref: str, sets_dir: Path | None = None) -> EvalSet:
    """`ref` is a set id under eval_sets/, or a path to a set.json."""
    p = Path(ref)
    if not (p.suffix == ".json" and p.exists()):
        p = (sets_dir or SETS_DIR) / ref / "set.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read evaluation set {ref!r}: {e}") from None
    for key in ("id", "repo", "bugs"):
        if key not in data:
            raise ValueError(f"{p}: missing {key!r}")
    bugs = []
    for b in data["bugs"]:
        if not b.get("id") or not b.get("title") or not b.get("locations"):
            raise ValueError(f"{p}: every bug needs id, title and locations (got {b.get('id')!r})")
        bugs.append(Bug(id=b["id"], title=b["title"], locations=b["locations"], cls=b.get("class", ""),
                        cwe=b.get("cwe", ""), notes=b.get("notes", "")))
    if len({b.id for b in bugs}) != len(bugs):
        raise ValueError(f"{p}: duplicate bug ids")
    return EvalSet(id=data["id"], title=data.get("title", data["id"]), role=data.get("role", "heldout"),
                   repo=data["repo"], bugs=bugs, language=data.get("language", ""), framework=data.get("framework", ""),
                   provenance=data.get("provenance", ""), contamination=data.get("contamination", ""),
                   variants=data.get("variants", {}), path=p)


def list_sets(sets_dir: Path | None = None) -> list[str]:
    d = sets_dir or SETS_DIR
    return sorted(p.parent.name for p in d.glob("*/set.json")) if d.is_dir() else []


# --------------------------------------------------------------------------- getting the repository
def _git(args: list[str], cwd: Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


def fetch(es: EvalSet, cache_dir: Path) -> Path:
    """The pristine checkout of the pinned commit (cloned on first use). The code is read, never run."""
    if "path" in es.repo:
        p = Path(es.repo["path"]).expanduser()
        if not p.is_dir():
            raise FileNotFoundError(f"{es.id}: local path {p} does not exist")
        return p
    commit = es.repo["commit"]
    target = cache_dir / es.id / commit[:12] / "raw"
    if (target / ".git").exists():
        head = _git(["rev-parse", "HEAD"], target)
        if head.startswith(commit) or commit.startswith(head):
            return target
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    sparse = es.repo.get("sparse")             # optional: only these paths (some repos have file names Windows cannot hold)
    _git(["clone", "--quiet", "--no-checkout", *(["--filter=blob:none"] if sparse else []), es.repo["url"], str(target)])
    try:
        if sparse:
            _git(["sparse-checkout", "set", "--no-cone", *sparse], target)
        _git(["checkout", "--quiet", commit], target)
        head = _git(["rev-parse", "HEAD"], target)
    except RuntimeError:
        shutil.rmtree(target, ignore_errors=True)
        raise
    if not (head.startswith(commit) or commit.startswith(head)):
        shutil.rmtree(target, ignore_errors=True)
        raise RuntimeError(f"{es.id}: checked out {head}, expected {commit}")
    return target


# --------------------------------------------------------------------------- removing leaks, keeping line numbers
def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path, pat.rstrip("/") + "/*") for pat in patterns)


SANITIZE_VERSION = 2          # part of a variant's cache key: changing the cleaning code must not reuse old copies


def _empty_comment(line: str) -> str:
    """The same comment line with its text removed but its delimiters kept. Blanking a `/*` or `*/` line outright would
    turn the commented-out code between them into live code, which is the opposite of cleaning."""
    s, indent = line.strip(), line[:len(line) - len(line.lstrip())]
    if s.startswith("//"):
        return indent + "//"
    if s.startswith("#"):
        return indent + "#"
    if s.startswith("<!--"):
        return indent + ("<!---->" if "-->" in s else "<!--")
    if s.startswith("/*"):
        return indent + ("/**/" if "*/" in s else "/*")
    if "*/" in s or "-->" in s:
        return indent + ("*/" if "*/" in s else "-->")
    return ""                                              # inside a block: an empty line is still inside it


def sanitize_text(path: str, text: str, spec: dict) -> str:
    """Apply a variant's line operations to one file. The number of lines never changes and a comment stays a comment."""
    lines = text.split("\n")
    drop_rx = [re.compile(r) for r in spec.get("blank_lines_matching", [])]
    comment_rx = [re.compile(r) for r in spec.get("blank_comment_lines_matching", [])]
    strip_rx = [re.compile(r) for r in spec.get("strip_regex", [])]
    mask = comment_mask(path, lines)
    for i, ln in enumerate(lines):
        if mask[i] and (spec.get("blank_all_comments") or any(r.search(ln) for r in comment_rx)
                        or any(r.search(ln) for r in drop_rx)):
            lines[i] = _empty_comment(ln)
        elif any(r.search(ln) for r in drop_rx):
            lines[i] = ""
        else:
            for r in strip_rx:
                ln = r.sub("", ln)
            lines[i] = ln
    return "\n".join(lines)


def materialize(es: EvalSet, variant: str, cache_dir: Path) -> Path:
    """The directory a run should read: the raw checkout, or a cleaned copy of it."""
    raw = fetch(es, cache_dir)
    if variant == "raw":
        return raw
    spec = es.variant(variant)
    digest = hashlib.sha1(json.dumps([SANITIZE_VERSION, spec], sort_keys=True).encode()).hexdigest()[:8]   # new recipe, new copy
    out = cache_dir / es.id / es.repo.get("commit", "local")[:12] / f"variant-{variant}-{digest}"
    if out.exists():
        return out
    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    drops = spec.get("drop_paths", [])
    for dirpath, dirs, names in os.walk(raw):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for name in names:
            src = Path(dirpath) / name
            rel = src.relative_to(raw).as_posix()
            if _matches(rel, drops) or is_secret_file(name):
                continue
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix.lower() in _TEXT_EXTS and src.stat().st_size < 1_500_000:
                try:
                    dst.write_text(sanitize_text(rel, src.read_text(encoding="utf-8"), spec), encoding="utf-8", newline="\n")
                    continue
                except UnicodeDecodeError:
                    pass
            shutil.copy2(src, dst)
    os.replace(tmp, out)
    return out


def validate_labels(es: EvalSet, variant: str, cache_dir: Path) -> list[str]:
    """Problems that would make scoring meaningless: a known bug whose file is gone from this variant, whose lines run past
    the end of the file, or whose lines are all blank (a cleaning recipe blanked the vulnerable code itself)."""
    root = materialize(es, variant, cache_dir)
    problems = []
    for b in es.bugs:
        usable = False
        for loc in b.locations:
            path = Path(root) / loc["file"]
            if not path.is_file():
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
            lo, hi = loc["lines"]
            if hi <= len(lines) and any(x.strip() for x in lines[lo - 1:hi]):
                usable = True
        if not usable:
            problems.append(f"{b.id}: no location has live code in variant {variant!r} ({b.title[:60]})")
    return problems


# --------------------------------------------------------------------------- facts about a set, before spending money
def describe(es: EvalSet, variant: str, cache_dir: Path) -> dict:
    """Size, routes, whether the source fits in one prompt, and a rough call budget for each arm."""
    from ..baseline import source_block
    from ..routemap import map_routes
    from ..routereview import plan

    root = materialize(es, variant, cache_dir)
    index = CodeIndex.from_dir(str(root))
    _, meta = source_block(index)
    rm = map_routes(index)
    reviews = len(plan(rm)) if rm.framework else 0
    claims = 15                                   # what the plain prompt is asked for; about 4 checking calls per claim
    return {
        "set": es.id, "variant": variant, "role": es.role, "files": len(index),
        "source_chars": sum(len(x) + 1 for p in index.paths() for x in index.lines(p)),
        "fits_in_one_prompt": not meta["left_out"], "files_that_did_not_fit": len(meta["left_out"]),
        "framework": rm.framework, "routes": len(rm.routes), "bugs": len(es.bugs),
        # rough: NodeGoat gave 30 candidates from 47 reviews, each checked with about 4 calls
        "calls_per_run": {"plain": 1 + claims * 4, "route-review": reviews + int(0.65 * reviews) * 4 if reviews else None},
        "contamination": es.contamination, "provenance": es.provenance,
    }
