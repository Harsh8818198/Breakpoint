"""Evaluation sets built from public security advisories: the code just before the maintainers' fix, labelled by the fix.

Why this exists. A teaching app announces its own bugs, and one reader (us) labelled the answers. A GitHub security
advisory with a fix commit gives both without us: the parent of the fix commit is the vulnerable code, the lines the fix
changed are where the flaw was, and the labeller was the maintainer. Choosing only fixes made *after* a model was released
means the model cannot have been trained on that fix.

Each set is one advisory: one repository pinned to the parent of the fix commit, one known flaw. The selection is mechanical and
recorded, including every advisory that was skipped and why, so nobody (including us) can say we picked the easy ones: every
filter below is applied from GitHub's data before a model sees a line of code, and candidates are taken in a fixed pseudo-random
order (`sha1(seed|ghsa)`), not by how promising they look. Nothing is cloned until a set is kept and a run needs the code.

What a fix commit cannot tell you: whether any *other* finding is a false claim. It labels one flaw. Precision on everything
else still needs a person to read the findings.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ..codeindex import BINARY_EXTS, IGNORE_DIRS, NOISE_NAMES, is_secret_file
from ..coderetrieval import file_weight

MODEL_RELEASE = "2026-03-03"            # gemini-3.1-flash-lite-preview launch (Google Cloud docs); knowledge cutoff January 2025
DEFAULT_SINCE = "2026-03-10"            # advisory published AND fix committed on or after this day: a week after the model existed
MAX_SOURCE_BYTES = 250_000              # the plain prompt holds 300,000 numbered characters; numbering adds about 15%
MAX_CHANGED_LINES = 80
MAX_CODE_FILES = 4
MAX_LOCATIONS = 8
SEVERITIES = ("high", "critical")

_SOURCE_EXTS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".py", ".rb", ".java", ".go", ".php", ".cs", ".rs", ".kt",
                ".scala", ".swift", ".html", ".htm", ".ejs", ".njk", ".vue", ".jinja", ".erb"}
_LANGUAGE = {"npm": "javascript", "pip": "python", "go": "go", "maven": "java", "composer": "php", "rubygems": "ruby",
             "rust": "rust", "nuget": "csharp"}
_CWE_CLASS = {
    "CWE-79": "xss", "CWE-80": "xss", "CWE-83": "xss", "CWE-87": "xss", "CWE-89": "injection", "CWE-564": "injection",
    "CWE-78": "injection", "CWE-77": "injection", "CWE-94": "injection", "CWE-95": "injection", "CWE-917": "injection",
    "CWE-74": "injection", "CWE-75": "injection", "CWE-90": "injection", "CWE-91": "injection", "CWE-113": "injection",
    "CWE-22": "path-traversal", "CWE-23": "path-traversal", "CWE-36": "path-traversal", "CWE-59": "path-traversal",
    "CWE-918": "ssrf", "CWE-502": "deserialization", "CWE-611": "xxe", "CWE-1321": "prototype-pollution",
    "CWE-400": "dos", "CWE-770": "dos", "CWE-1333": "dos", "CWE-407": "dos", "CWE-674": "dos", "CWE-835": "dos", "CWE-476": "dos",
    "CWE-601": "redirect", "CWE-862": "authorization", "CWE-863": "authorization", "CWE-285": "authorization",
    "CWE-639": "authorization", "CWE-284": "authorization", "CWE-269": "authorization", "CWE-287": "authentication",
    "CWE-306": "authentication", "CWE-288": "authentication", "CWE-290": "authentication", "CWE-352": "csrf",
    "CWE-200": "disclosure", "CWE-209": "disclosure", "CWE-532": "disclosure", "CWE-327": "crypto", "CWE-328": "crypto",
    "CWE-330": "crypto", "CWE-338": "crypto", "CWE-347": "crypto", "CWE-20": "input-validation", "CWE-434": "upload",
}


class Skip(Exception):
    """An advisory that cannot become a set, with the reason recorded in the selection log."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


# --------------------------------------------------------------------------- the GitHub advisory database
def _token() -> str | None:
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    try:                                                       # the GitHub CLI's login, when there is one
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def api_get(url: str, params: dict | None = None) -> tuple[object, str | None]:
    """One GET against api.github.com: (parsed JSON, url of the next page or None). Public data; a token only raises the rate limit."""
    if not url.startswith("http"):
        url = "https://api.github.com/" + url.lstrip("/")
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "breakpoint-eval"}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
            nxt = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", "") or "")
            return json.loads(r.read().decode("utf-8")), (nxt.group(1) if nxt else None)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise RuntimeError(f"GitHub API refused ({e.code}): probably the rate limit; set GH_TOKEN or run `gh auth login`") from None
        raise RuntimeError(f"GitHub API answered {e.code} for {url}") from None
    except (urllib.error.URLError, ValueError) as e:
        raise RuntimeError(f"cannot reach the GitHub API ({e})") from None


def list_advisories(ecosystem: str, severity: str, since: str, cap: int = 600) -> list[dict]:
    """Reviewed advisories of one severity published on or after `since`, newest first, up to `cap`."""
    out: list[dict] = []
    url: str | None = "advisories"
    params: dict | None = {"ecosystem": ecosystem, "type": "reviewed", "severity": severity, "published": f">={since}", "per_page": 100}
    while url and len(out) < cap:
        page, url = api_get(url, params)
        params = None                                          # the next-page url already carries them
        out += [a for a in page if not a.get("withdrawn_at")]
    return out[:cap]


def get_advisory(ghsa_id: str) -> dict:
    data, _ = api_get(f"advisories/{ghsa_id}")
    if not isinstance(data, dict) or not data.get("ghsa_id"):
        raise ValueError(f"{ghsa_id}: not an advisory")
    return data


def shuffled(advisories: list[dict], seed: str) -> list[dict]:
    """A fixed order that depends only on the seed and the advisory id, never on what the advisory is about."""
    return sorted(advisories, key=lambda a: hashlib.sha1(f"{seed}|{a['ghsa_id']}".encode()).hexdigest())


_COMMIT_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/commit/([0-9a-f]{40})(?:[/?#].*)?$")


def fix_commits(adv: dict) -> list[tuple[str, str, str]]:
    """(owner, repo, sha) of every full-length commit url in the advisory's references, without duplicates."""
    seen: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    for ref in adv.get("references") or []:
        m = _COMMIT_URL.match((ref or "").strip())
        if m:
            seen.setdefault((m.group(1).lower(), m.group(2).lower(), m.group(3)), (m.group(1), m.group(2), m.group(3)))
    return list(seen.values())


def advisory_class(adv: dict) -> tuple[str, str]:
    """(coarse class, first CWE id) from the advisory's CWE list."""
    cwes = [c.get("cwe_id", "") for c in ((adv.get("cwes") or []) if isinstance(adv.get("cwes"), list) else [])]
    for c in cwes:
        if c in _CWE_CLASS:
            return _CWE_CLASS[c], c
    return "other", (cwes[0] if cwes else "")


# --------------------------------------------------------------------------- the fix commit, read from GitHub's data
def is_source(path: str) -> bool:
    """A file whose change is a change to the project's own program (not a test, doc, vendored copy or lockfile)."""
    name = path.rsplit("/", 1)[-1]
    return (os.path.splitext(name)[1].lower() in _SOURCE_EXTS and file_weight(path) >= 0.5 and not is_secret_file(name))


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def old_ranges(patch: str) -> list[tuple[int, int, bool]]:
    """(first line, last line, addition_only) in the OLD file for every block of changed lines in a unified diff of one file.
    A block that only adds lines has no old lines; it is anchored on the single line just before the insertion."""
    out: list[tuple[int, int, bool]] = []
    old, lo, hi, anchor = 0, None, None, 0
    code_removed = code_added = False                           # a block of only blank lines is formatting, not a fix

    def flush():
        nonlocal lo, hi, code_removed, code_added
        if lo is not None and code_removed:
            out.append((lo, hi, False))
        elif code_added:
            out.append((max(1, anchor if lo is None else lo - 1), max(1, anchor if lo is None else lo - 1), True))
        lo = hi = None
        code_removed = code_added = False

    for line in patch.split("\n"):
        m = _HUNK.match(line)
        if m:
            flush()
            old = int(m.group(1))
        elif line.startswith("-"):                              # GitHub's per-file patch has no ---/+++ header, so no line is one
            lo = old if lo is None else lo
            hi = old
            code_removed = code_removed or bool(line[1:].strip())
            old += 1
        elif line.startswith("+"):
            if lo is None and not code_added:
                anchor = old - 1
            code_added = code_added or bool(line[1:].strip())
        elif line.startswith(" "):
            flush()
            old += 1
    flush()
    return out


def merge_ranges(ranges: list[tuple[int, int, bool]], gap: int = 3) -> list[tuple[int, int, bool]]:
    out: list[tuple[int, int, bool]] = []
    for lo, hi, add in sorted(ranges):
        if out and lo <= out[-1][1] + gap:
            out[-1] = (out[-1][0], max(out[-1][1], hi), out[-1][2] and add)
        else:
            out.append((lo, hi, add))
    return out


def prompt_bytes(tree: list[dict]) -> int:
    """Bytes of the files the plain prompt would show (project files of weight >= 0.5; no binaries, lockfiles or vendored code)."""
    total = 0
    for entry in tree:
        path = entry.get("path", "")
        if entry.get("type") != "blob" or not isinstance(entry.get("size"), int):
            continue
        segs = path.split("/")
        name = segs[-1]
        if any(s in IGNORE_DIRS for s in segs[:-1]) or os.path.splitext(name)[1].lower() in BINARY_EXTS:
            continue
        if any(re.fullmatch(re.escape(n).replace(r"\*", ".*"), name.lower()) for n in NOISE_NAMES) or is_secret_file(name):
            continue
        if file_weight(path) >= 0.5:
            total += entry["size"]
    return total


def inspect_fix(owner: str, repo: str, sha: str, max_source_bytes: int = MAX_SOURCE_BYTES) -> dict:
    """Facts about a fix commit and the labels it implies, from GitHub's commit and tree data. Raises Skip when the commit cannot make
    a clean set. Nothing is cloned."""
    commit, _ = api_get(f"repos/{owner}/{repo}/commits/{sha}")
    parents = [p["sha"] for p in commit.get("parents") or []]
    if len(parents) != 1:
        raise Skip("merge_or_root_commit", f"{len(parents)} parents")
    parent = parents[0]
    date = ((commit.get("commit") or {}).get("committer") or {}).get("date") or ""
    files = commit.get("files") or []
    if len(files) >= 300:
        raise Skip("fix_too_large", "300 or more files")
    code = [f for f in files if f.get("status") != "added" and is_source(f.get("previous_filename") or f["filename"])] + \
           [f for f in files if f.get("status") == "added" and is_source(f["filename"])]
    other = len(files) - len(code)
    if not code:
        raise Skip("no_source_change", f"{other} non-source file(s) changed")
    if len(code) > MAX_CODE_FILES:
        raise Skip("too_many_files", f"{len(code)} source files")
    changed = sum(f.get("additions", 0) + f.get("deletions", 0) for f in code)
    if changed > MAX_CHANGED_LINES:
        raise Skip("fix_too_large", f"{changed} changed lines")
    tree, _ = api_get(f"repos/{owner}/{repo}/git/trees/{parent}", {"recursive": "1"})
    if tree.get("truncated"):
        raise Skip("source_too_big_for_one_prompt", "tree too large to list")
    size = prompt_bytes(tree.get("tree") or [])
    if size > max_source_bytes:
        raise Skip("source_too_big_for_one_prompt", f"{size // 1000} KB")
    locations, addition_only = [], True
    for f in code:
        if f.get("status") == "added":
            continue                                                # a file the fix creates: nothing to point at in the old code
        if not f.get("patch"):
            raise Skip("patch_not_available", f["filename"])
        for lo, hi, add in merge_ranges(old_ranges(f["patch"])):
            locations.append({"file": f.get("previous_filename") or f["filename"], "lines": [lo, hi]})
            addition_only = addition_only and add
    if not locations:
        raise Skip("no_old_lines", "the fix only creates new files")
    if len(locations) > MAX_LOCATIONS:
        raise Skip("diff_too_spread", f"{len(locations)} places")
    return {"parent": parent, "date": date, "locations": locations, "addition_only": addition_only, "changed_lines": changed,
            "source_bytes": size, "source_files_changed": [f["filename"] for f in code], "other_files_changed": other}


def build_set(adv: dict, *, fixed_since: str = DEFAULT_SINCE, max_source_bytes: int = MAX_SOURCE_BYTES) -> dict:
    """The set.json content for one advisory, or Skip. Applies every filter before anything is sent to a model."""
    ghsa = adv["ghsa_id"]
    if (adv.get("published_at") or "")[:10] < fixed_since:
        raise Skip("advisory_before_cutoff", (adv.get("published_at") or "")[:10])
    m = re.match(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", adv.get("source_code_location") or "")
    if not m:
        raise Skip("no_github_source_location")
    commits = fix_commits(adv)
    if not commits:
        raise Skip("no_fix_commit_in_references")
    own = [c for c in commits if (c[0].lower(), c[1].lower()) == (m.group(1).lower(), m.group(2).lower())]
    if not own:
        raise Skip("fix_commit_in_another_repository")
    if len(own) > 1:
        raise Skip("several_fix_commits", f"{len(own)}")
    owner, repo, sha = own[0]
    info = inspect_fix(owner, repo, sha, max_source_bytes)
    if info["date"][:10] < fixed_since:
        raise Skip("fix_before_cutoff", info["date"][:10])
    cls, cwe = advisory_class(adv)
    vuln = (adv.get("vulnerabilities") or [{}])[0]
    package = ((vuln.get("package") or {}).get("name")) or repo
    ecosystem = (vuln.get("package") or {}).get("ecosystem") or ""
    note = ("The fix only adds code, so the label is the line just before the insertion; a correct finding may point at the unprotected "
            "code a few lines on, or elsewhere in the same function. " if info["addition_only"] else "") + \
        "Judge a finding against the advisory text in `history`, not only against the lines."
    return {
        "id": ghsa.lower(), "title": f"{package}: {adv.get('summary', '')}"[:160], "role": "heldout",
        "repo": {"url": f"https://github.com/{owner}/{repo}", "commit": info["parent"], "partial": True},
        "language": _LANGUAGE.get(ecosystem.lower(), ""), "framework": "",
        "provenance": ("Labels come from the maintainers' fix commit, not from a model: the lines it changed or removed in its parent "
                       f"commit (advisory {ghsa}). Whether the patch really addresses the advisory is recorded in history.label_review."),
        "contamination": (f"Advisory published {(adv.get('published_at') or '')[:10]} and fix committed {info['date'][:10]}, both on or after "
                          f"{fixed_since}, after the {MODEL_RELEASE} release of gemini-3.1-flash-lite (knowledge cutoff January 2025): that model "
                          "cannot have trained on this fix. A model with a later cutoff might have. The code may still resemble earlier "
                          "public fixes of similar bugs in the same project."),
        "bugs": [{"id": ghsa.lower(), "title": adv.get("summary", ghsa)[:200], "class": cls, "cwe": cwe,
                  "locations": info["locations"], "notes": note}],
        "variants": {},
        "history": {
            "advisory": ghsa, "advisory_url": adv.get("html_url", ""), "severity": adv.get("severity", ""),
            "published": (adv.get("published_at") or "")[:10], "package": package, "ecosystem": ecosystem,
            "vulnerable_versions": vuln.get("vulnerable_version_range", ""),
            "patched": vuln.get("first_patched_version") or "",
            "fix_commit": sha, "fix_url": f"https://github.com/{owner}/{repo}/commit/{sha}", "fix_date": info["date"],
            "changed_lines": info["changed_lines"], "source_files_changed": info["source_files_changed"],
            "other_files_changed": info["other_files_changed"], "addition_only": info["addition_only"],
            "source_bytes": info["source_bytes"], "fits_in_one_prompt": True,
            "description": (adv.get("description") or "")[:4000], "label_review": "not reviewed"},
    }


# --------------------------------------------------------------------------- choosing sets, with a record of every choice
def harvest(ecosystems: list[str], since: str, count: int, seed: str, out_dir: Path, *, severities=SEVERITIES,
            max_considered: int = 120, max_source_bytes: int = MAX_SOURCE_BYTES, log=print) -> dict:
    """Build up to `count` sets under out_dir/<ghsa>/set.json from a fixed-order walk through the advisories. Writes
    out_dir/selection.json, which lists every advisory that was considered and what happened to it."""
    pool: list[dict] = []
    for eco in ecosystems:
        for sev in severities:
            pool += [dict(a, _ecosystem=eco) for a in list_advisories(eco, sev, since)]
    pool = shuffled(pool, seed)
    log(f"{len(pool)} reviewed {'/'.join(severities)} advisories published since {since} in {', '.join(ecosystems)}; seed {seed!r}")
    considered, built = [], []
    for adv in pool:
        if len(built) >= count or len(considered) >= max_considered:
            break
        ghsa = adv["ghsa_id"]
        target = out_dir / ghsa.lower() / "set.json"
        try:
            if target.exists():
                built.append(ghsa)
                considered.append({"advisory": ghsa, "outcome": "kept", "note": "already built"})
                log(f"  {ghsa}: already built")
                continue
            data = build_set(adv, fixed_since=since, max_source_bytes=max_source_bytes)
        except Skip as e:
            considered.append({"advisory": ghsa, "outcome": "skipped", "reason": e.reason, "detail": e.detail})
            log(f"  {ghsa}: skipped ({e})")
            continue
        except RuntimeError as e:                               # network trouble on one advisory: record, go on
            considered.append({"advisory": ghsa, "outcome": "skipped", "reason": "error", "detail": str(e)[:200]})
            log(f"  {ghsa}: skipped (error: {str(e)[:100]})")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        built.append(ghsa)
        considered.append({"advisory": ghsa, "outcome": "kept", "package": data["history"]["package"], "class": data["bugs"][0]["class"]})
        log(f"  {ghsa}: kept ({data['history']['package']}, {data['bugs'][0]['class']}, {len(data['bugs'][0]['locations'])} place(s))")
    record = {"parameters": {"ecosystems": ecosystems, "severities": list(severities), "since": since, "seed": seed, "count": count,
                             "max_considered": max_considered, "max_source_bytes": max_source_bytes, "model_release": MODEL_RELEASE},
              "pool": len(pool), "considered": considered, "kept": built}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "selection.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record
