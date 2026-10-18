"""Known-bug labels from maintainer-written markers (OWASP Juice Shop's `vuln-code-snippet`).

Juice Shop marks the vulnerable lines of its coding challenges in the source itself:

    models.sequelize.query(`SELECT ...`) // vuln-code-snippet vuln-line loginAdminChallenge loginBenderChallenge

Those markers are ground truth that someone other than us wrote. They are also a leak: a model that reads them is
handed the answer. So the markers are read here, once, from the pristine checkout to make labels, and the evaluation
variant removes them (see sets.py `strip_regex`) while keeping every line number.
"""

from __future__ import annotations

import re
from pathlib import Path

_MARK = re.compile(r"vuln-code-snippet\s+(start|end|vuln-line|neutral-line|hide-line)\b([\w\s]*)")
_CODE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".rb", ".java", ".go", ".php", ".cs", ".yml", ".yaml"}
_SKIP = {".git", "node_modules", "dist", "build"}


def challenge_names(yml_text: str) -> dict[str, dict]:
    """key -> {"name", "category"} from Juice Shop's challenges.yml (read with plain regexes; no YAML library needed)."""
    out: dict[str, dict] = {}
    for block in re.split(r"(?m)^-\s+(?=name:)", yml_text):
        name = re.search(r"(?m)^\s*name:\s*(.+?)\s*$", block)
        key = re.search(r"(?m)^\s*key:\s*['\"]?(\w+)['\"]?\s*$", block)
        cat = re.search(r"(?m)^\s*category:\s*(.+?)\s*$", block)
        if name and key:
            out[key.group(1)] = {"name": name.group(1).strip("'\" "), "category": (cat.group(1).strip("'\" ") if cat else "")}
    return out


def _ranges(lines: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for n in sorted(set(lines)):
        if out and n <= out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def labels_from_snippets(root: str | Path, challenges_yml: str | Path | None = None) -> list[dict]:
    """One bug per group of challenge keys that mark exactly the same lines (three login challenges share one SQL
    injection, which is one bug here, not three)."""
    root = Path(root)
    hits: dict[str, dict[str, list[int]]] = {}                      # key -> file -> vulnerable lines
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in _CODE_EXTS or any(part in _SKIP for part in p.relative_to(root).parts):
            continue
        try:
            lines = p.read_text(encoding="utf-8").split("\n")
        except (UnicodeDecodeError, OSError):
            continue
        rel = p.relative_to(root).as_posix()
        for i, ln in enumerate(lines, 1):
            m = _MARK.search(ln)
            if not m or m.group(1) != "vuln-line":
                continue
            before = ln[:m.start()].strip().rstrip("/#").strip()
            target = i if before else i + 1                        # a marker alone on its line points at the next line
            for key in m.group(2).split():
                hits.setdefault(key, {}).setdefault(rel, []).append(target)
    names = challenge_names(Path(challenges_yml).read_text(encoding="utf-8")) if challenges_yml else {}
    groups: dict[tuple, list[str]] = {}
    for key, files in hits.items():
        sig = tuple(sorted((f, tuple(map(tuple, _ranges(ls)))) for f, ls in files.items()))
        groups.setdefault(sig, []).append(key)
    bugs = []
    for sig, keys in sorted(groups.items(), key=lambda kv: kv[1][0]):
        keys = sorted(keys)
        first = names.get(keys[0], {})
        title = first.get("name") or keys[0]
        extra = [names.get(k, {}).get("name", k) for k in keys[1:]]
        bugs.append({"id": keys[0], "title": title + (f" (same lines also mark: {', '.join(extra)})" if extra else ""),
                     "class": first.get("category", ""), "cwe": "",
                     "locations": [{"file": f, "lines": list(r)} for f, rs in sig for r in rs],
                     "notes": "challenge keys: " + ", ".join(keys)})
    return bugs
