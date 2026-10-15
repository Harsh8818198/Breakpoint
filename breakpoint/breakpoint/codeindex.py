"""Read-only index of a repository's source, used to check claims against the real code.

Why this exists: findings are written by LLM agents that only see a short summary of the code, so they
routinely claim protections are missing that are a few lines past what they read. This index lets a
verifier read the *actual* files, and lets us check mechanically that any code a verdict quotes really
exists in the file it names.

Nothing here executes repository code. Secret-bearing files (.env, keys, ...) are never read, and
secret-looking values are redacted from everything that is rendered, quoted or sent to a model.
"""

from __future__ import annotations

import bisect
import fnmatch
import math
import os
import re
from pathlib import Path

IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".next", "__pycache__", "venv", ".venv",
    "dist", "build", "target", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".idea",
    ".vscode", ".gradle", "coverage", ".cache", "site-packages",
}

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg", ".pdf", ".zip", ".tar", ".gz",
    ".tgz", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".bin", ".class", ".jar", ".pyc", ".o",
    ".a", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".mov", ".avi", ".wav",
    ".onnx", ".pt", ".pkl", ".npy", ".db", ".sqlite", ".sqlite3", ".iso", ".msi", ".map",
}

NOISE_NAMES = (
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "cargo.lock", "gemfile.lock",
    "composer.lock", "*.min.js", "*.min.css",
)

# Files that hold secrets. They are never read, never indexed, never sent to a model.
SECRET_NAMES = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "id_rsa*",
    "id_ed25519*", "id_dsa*", "*key*.hex", ".npmrc", ".pypirc", ".netrc", "credentials*.json",
    "secrets*.json", "secrets.*", "*.secret", "*.secrets", "service-account*.json",
)
_SAFE_ENV = {".env.example", ".env.sample", ".env.template", ".env.dist", ".env.defaults"}


def is_secret_file(name: str) -> bool:
    """True for files that normally contain credentials. `.env.example`-style templates are fine."""
    n = name.lower()
    if n in _SAFE_ENV:
        return False
    return any(fnmatch.fnmatch(n, pat) for pat in SECRET_NAMES)


# --------------------------------------------------------------------------- redaction
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)")
_TOKEN_FORMATS = re.compile(
    r"\bsk-[A-Za-z0-9_\-]{20,}|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}|"
    r"\bxox[abpr]-[A-Za-z0-9\-]{10,}|\bAIza[0-9A-Za-z_\-]{35}|\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
)
_ASSIGNED_SECRET = re.compile(
    r"""(?ix)(\b\w*(?:api[_-]?key|secret|token|passw(?:or)?d|pwd|private[_-]?key)\w*["']?\s*[:=]\s*)"""
    r"""(["'])([^"'\s]{10,})\2"""
)


def _keep_newlines(m: re.Match, label: str) -> str:
    return label + "\n" * m.group(0).count("\n")


def _assigned(m: re.Match) -> str:
    value = m.group(3)
    # Only values that look like real secrets; plain identifiers such as "token_in_keyring" stay readable.
    if any(c.isdigit() for c in value) and any(c.isalpha() for c in value):
        return f"{m.group(1)}{m.group(2)}[REDACTED]{m.group(2)}"
    return m.group(0)


def redact_text(text: str) -> str:
    """Replace secret-looking values. Preserves the number of lines so line numbers stay true."""
    text = _PRIVATE_KEY.sub(lambda m: _keep_newlines(m, "[REDACTED PRIVATE KEY]"), text)
    text = _TOKEN_FORMATS.sub("[REDACTED]", text)
    return _ASSIGNED_SECRET.sub(_assigned, text)


# --------------------------------------------------------------------------- the index
_MAX_LINE = 400
_SPACE = re.compile(r"\s+")
_LINE_PREFIX = re.compile(r"^\s*\d+c?\s*[|:]\s?")       # "  12| " or, for a comment line, "  12c| "

_HASH_COMMENT_EXTS = {".py", ".rb", ".sh", ".bash", ".zsh", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf",
                      ".pl", ".r", ".ps1", ".env", ".dockerfile", ".mk", ".tf"}
_SLASH_COMMENT_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".go", ".c", ".h", ".cc", ".cpp", ".hpp",
                       ".cs", ".php", ".rs", ".swift", ".kt", ".scala", ".css", ".scss", ".dart"}
_MARKUP_EXTS = {".html", ".htm", ".xml", ".vue", ".svelte", ".njk", ".jinja", ".erb"}


def comment_mask(path: str, lines: list[str]) -> list[bool]:
    """True for lines that are entirely comment. Code with a trailing comment is NOT masked.
    Heuristic by file type: // and /* */ for C-like, # for scripting languages, <!-- --> for markup."""
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path).lower()
    mask = [False] * len(lines)
    if ext in _HASH_COMMENT_EXTS or name in ("dockerfile", "makefile"):
        return [ln.lstrip().startswith("#") for ln in lines]
    if ext in _SLASH_COMMENT_EXTS:
        opener, closer, single = "/*", "*/", "//"
    elif ext in _MARKUP_EXTS:
        opener, closer, single = "<!--", "-->", None
    else:
        return mask
    inside = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if inside:
            mask[i] = True
            inside = closer not in s
        elif s.startswith(opener):
            mask[i] = True
            inside = closer not in s[len(opener):]
        elif single and s.startswith(single):
            mask[i] = True
    return mask


def normalize(s: str) -> str:
    return _SPACE.sub(" ", s).strip()


def strip_line_numbers(quote: str) -> str:
    """Models sometimes copy the `  123| ` gutter into a quote; drop it."""
    return "\n".join(_LINE_PREFIX.sub("", ln) for ln in quote.splitlines())


class CodeIndex:
    def __init__(self, root: str, files: dict[str, list[str]], skipped: dict[str, int] | None = None):
        self.root = root
        self._files = files
        self.skipped = skipped or {}
        self._lower: dict[str, str] = {}
        self._norm: dict[str, tuple[str, list[int]]] = {}
        self._masks: dict[str, list[bool]] = {}

    # ---- construction
    @classmethod
    def from_dir(cls, root: str, *, max_file_bytes: int = 300_000, max_files: int = 4000,
                 max_total_bytes: int = 30_000_000) -> "CodeIndex":
        base = Path(root).resolve()
        if not base.is_dir():
            raise ValueError(f"Not a directory: {root}")
        files: dict[str, list[str]] = {}
        skipped = {"secret": 0, "binary": 0, "too_large": 0, "noise": 0, "limit": 0, "unreadable": 0}
        total = 0
        for dirpath, dirs, names in os.walk(base, followlinks=False):
            # virtualenvs are recognised by their marker file, not by a name like 'env' (config/env/ is real code)
            dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS
                             and not os.path.exists(os.path.join(dirpath, d, "pyvenv.cfg")))
            for name in sorted(names):
                full = Path(dirpath) / name
                lname = name.lower()
                if is_secret_file(name):
                    skipped["secret"] += 1
                    continue
                if full.suffix.lower() in BINARY_EXTS:
                    skipped["binary"] += 1
                    continue
                if any(fnmatch.fnmatch(lname, pat) for pat in NOISE_NAMES):
                    skipped["noise"] += 1
                    continue
                if full.is_symlink():
                    continue
                try:
                    size = full.stat().st_size
                    if size > max_file_bytes:
                        skipped["too_large"] += 1
                        continue
                    if len(files) >= max_files or total + size > max_total_bytes:
                        skipped["limit"] += 1
                        continue
                    raw = full.read_bytes()
                except OSError:
                    skipped["unreadable"] += 1
                    continue
                if b"\x00" in raw[:2048]:
                    skipped["binary"] += 1
                    continue
                total += size
                rel = full.relative_to(base).as_posix()
                text = redact_text(raw.decode("utf-8", errors="replace"))
                files[rel] = text.splitlines()
        return cls(str(base), files, skipped)

    # ---- basic access
    def __len__(self) -> int:
        return len(self._files)

    def paths(self) -> list[str]:
        return list(self._files)

    def has(self, path: str) -> bool:
        return path in self._files

    def lines(self, path: str) -> list[str]:
        return self._files[path]

    def resolve_path(self, p: str) -> str | None:
        """Map a model-supplied path onto a real indexed path, or None. Never touches the disk."""
        if not isinstance(p, str):
            return None
        p = p.strip().replace("\\", "/")
        while p.startswith("./"):
            p = p[2:]
        p = p.lstrip("/")
        if p in self._files:
            return p
        tail = [f for f in self._files if f.endswith("/" + p) or f == p]
        if len(tail) == 1:
            return tail[0]
        base = p.rsplit("/", 1)[-1]
        same = [f for f in self._files if f.rsplit("/", 1)[-1] == base]
        return same[0] if len(same) == 1 else None

    # ---- search
    def is_comment(self, path: str, line: int) -> bool:
        """True if 1-based `line` of `path` is entirely a comment (so it is not active code)."""
        mask = self._masks.get(path)
        if mask is None:
            mask = self._masks[path] = comment_mask(path, self._files[path])
        return 0 < line <= len(mask) and mask[line - 1]

    def span_is_comment(self, path: str, line: int, quote: str) -> bool:
        """True if every line the quote covers (starting at `line`) is a comment."""
        n = max(1, len([ln for ln in strip_line_numbers(quote).splitlines() if ln.strip()]))
        return all(self.is_comment(path, line + k) for k in range(n))

    def _lower_text(self, path: str) -> str:
        t = self._lower.get(path)
        if t is None:
            t = self._lower[path] = "\n".join(self._files[path]).lower()
        return t

    def grep(self, term: str, *, max_per_file: int = 6) -> dict[str, list[int]]:
        """Literal, case-insensitive search. Returns {path: [1-based line numbers]}."""
        t = term.strip().lower()
        if len(t) < 3:
            return {}
        out: dict[str, list[int]] = {}
        for path, lines in self._files.items():
            if t not in self._lower_text(path):
                continue
            hits = [i + 1 for i, ln in enumerate(lines) if t in ln.lower()]
            if hits:
                out[path] = hits[:max_per_file]
        return out

    def rank_files(self, terms: list[str], preferred: list[str] | None = None, limit: int = 8) -> list[tuple[str, list[int]]]:
        """Files most relevant to `terms` (rarer terms count more), with the lines that matched."""
        n = max(len(self._files), 1)
        score: dict[str, float] = {}
        hit_lines: dict[str, set[int]] = {}
        for term in terms:
            hits = self.grep(term)
            if not hits:
                continue
            weight = 1.0 / (1.0 + math.log(len(hits)))       # a term found everywhere says little
            if len(hits) > 0.4 * n and n > 10:
                continue
            for path, lines in hits.items():
                score[path] = score.get(path, 0.0) + weight * min(len(lines), 3)
                hit_lines.setdefault(path, set()).update(lines)
        for p in preferred or []:
            score[p] = score.get(p, 0.0) + 100.0
            hit_lines.setdefault(p, set())
        ranked = sorted(score, key=lambda p: (-score[p], p))[:limit]
        return [(p, sorted(hit_lines[p])) for p in ranked]

    # ---- following calls (so a verdict about a call site can see what the callee really does)
    _DEF = {}   # name -> compiled regex, shared

    def find_definitions(self, name: str, limit: int = 4) -> list[tuple[str, int]]:
        """Where `name` is defined (Python def/class, JS/TS function or arrow/method, Go func)."""
        rx = CodeIndex._DEF.get(name)
        if rx is None:
            n = re.escape(name)
            rx = CodeIndex._DEF[name] = re.compile(
                rf"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:def|class|function\*?|func(?:\s*\([^)]*\))?)\s+{n}\b"
                rf"|^\s*(?:export\s+)?(?:const|let|var)\s+{n}\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|\w+\s*=>)"
                rf"|^\s*(?:public\s+|private\s+|static\s+|async\s+)*{n}\s*\([^)]*\)\s*(?::\s*[\w<>\[\]|. ]+)?\s*\{{")
        out: list[tuple[str, int]] = []
        for path, lines in self._files.items():
            if name not in self._lower_text(path) and name.lower() not in self._lower_text(path):
                continue
            for i, ln in enumerate(lines):
                if rx.search(ln):
                    out.append((path, i + 1))
                    if len(out) >= limit:
                        return out
        return out

    def callee_hits(self, texts: list[str], depth: int = 2, max_defs: int = 10, window: int = 45) -> dict[str, list[int]]:
        """Definitions of the functions that `texts` call, then of the functions *those* call.
        Returns {path: [definition lines]} ready to pass to `excerpt`."""
        found: dict[str, list[int]] = {}
        seen_names: set[str] = set()
        frontier = list(texts)
        count = 0
        for _ in range(depth):
            nxt: list[str] = []
            for text in frontier:
                for name in called_names(text):
                    if name in seen_names or count >= max_defs:
                        continue
                    seen_names.add(name)
                    defs = self.find_definitions(name)
                    if not defs or len(defs) > 3:           # undefined here (library) or too generic to follow
                        continue
                    for path, line in defs:
                        found.setdefault(path, []).append(line)
                        body = "\n".join(self._files[path][line - 1: line - 1 + window])
                        nxt.append(body)
                        count += 1
            frontier = nxt
        return found

    # ---- rendering
    def excerpt(self, path: str, hit_lines: list[int] | None = None, *, whole_if_chars: int = 24000,
                max_chars: int = 16000, pad: int = 35) -> str:
        """Numbered source for `path`. A file up to `whole_if_chars` is always shown in full; a larger one
        is shown as windows around the hit lines, which shrink until they fit in `max_chars`."""
        lines = self._files[path]
        size = sum(len(x) + 1 for x in lines)
        if size <= whole_if_chars:
            return self._render(path, [(1, len(lines))], limit=None)
        text = ""
        for p in (pad, 20, 10, 4):
            ranges = [(1, min(25, len(lines)))]                   # imports / top-of-file context
            ranges += [(max(1, h - p), min(len(lines), h + p)) for h in hit_lines or []]
            text = self._render(path, _merge(ranges), limit=max_chars)
            if "[truncated]" not in text:
                return text
        return text

    def _render(self, path: str, ranges: list[tuple[int, int]], limit: int | None) -> str:
        lines, out, used = self._files[path], [], 0
        for a, b in ranges:
            if out:
                out.append("      | ...")
            for n in range(a, b + 1):
                row = f"{n:>5}{'c' if self.is_comment(path, n) else ''}| {lines[n - 1][:_MAX_LINE]}"
                used += len(row) + 1
                if limit is not None and used > limit:
                    out.append("      | ... [truncated]")
                    return f"### {path}\n" + "\n".join(out)
                out.append(row)
        return f"### {path}\n" + "\n".join(out)

    def file_listing(self, terms: list[str], limit: int = 400) -> str:
        """Compact path list for the model; paths sharing words with the claim come first."""
        words = {w for t in terms for w in re.split(r"[^a-z0-9]+", t.lower()) if len(w) >= 3}

        def rel(p: str) -> int:
            parts = set(re.split(r"[^a-z0-9]+", p.lower()))
            return -len(words & parts)

        paths = sorted(self._files, key=lambda p: (rel(p), p))[:limit]
        more = len(self._files) - len(paths)
        rows = [f"{p} ({len(self._files[p])} lines)" for p in paths]
        if more > 0:
            rows.append(f"... and {more} more files")
        return "\n".join(rows)

    # ---- quote verification (the mechanical part of every verdict)
    def _normalized(self, path: str, skip_comments: bool = False) -> tuple[str, list[int], list[int]]:
        """(text, start offset of each kept line, 1-based line number of each kept line)."""
        key = (path, skip_comments)
        cached = self._norm.get(key)
        if cached is None:
            starts, linenos, parts, pos = [], [], [], 0
            for i, ln in enumerate(self._files[path]):
                if skip_comments and self.is_comment(path, i + 1):
                    continue
                n = normalize(ln)
                if not n:                      # blank lines would leave double spaces that no quote contains
                    continue
                starts.append(pos)
                linenos.append(i + 1)
                parts.append(n)
                pos += len(n) + 1
            cached = self._norm[key] = (" ".join(parts), starts, linenos)
        return cached

    def find_quote(self, path: str, quote: str, near: int | None = None, min_chars: int = 12) -> int | None:
        """1-based line where `quote` really occurs in `path` (whitespace-insensitive), else None.

        Tolerates the two ways a model naturally abbreviates a quote: `...` between pieces, and leaving out
        comment lines that sit between the lines it copies. Every piece must still exist, in order and close
        together. Quotes shorter than `min_chars` are rejected: `}` or `return` would 'match' anywhere."""
        if path not in self._files or not isinstance(quote, str):
            return None
        raw = strip_line_numbers(quote)
        pieces = [normalize(x) for x in re.split(r"\.\.\.|…", raw)]
        pieces = [x for x in pieces if len(x) >= 6]
        if not pieces or sum(len(x) for x in pieces) < min_chars:
            return None
        for skip in (False, True):
            text, starts, linenos = self._normalized(path, skip)
            lines = []
            first, i = pieces[0], text.find(pieces[0])
            while i != -1 and len(lines) < 50:
                if self._chain_follows(text, i + len(first), pieces[1:]):
                    lines.append(linenos[bisect.bisect_right(starts, i) - 1])
                i = text.find(first, i + 1)
            if lines:
                return lines[0] if near is None else min(lines, key=lambda ln: abs(ln - near))
        return None

    @staticmethod
    def _chain_follows(text: str, pos: int, rest: list[str], max_gap: int = 700) -> bool:
        for piece in rest:
            j = text.find(piece, pos, pos + max_gap + len(piece))
            if j == -1:
                return False
            pos = j + len(piece)
        return True


_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{3,})\s*\(")
_NOT_FUNCTIONS = {
    "print", "len", "str", "int", "float", "dict", "list", "set", "tuple", "range", "isinstance", "super",
    "open", "return", "while", "with", "except", "raise", "assert", "lambda", "function", "catch", "switch",
    "elif", "else", "when", "bool", "bytes", "type", "enumerate", "zip", "sorted", "reversed", "any", "all",
    "min", "max", "sum", "format", "join", "split", "strip", "append", "extend", "update", "pop", "get",
    "items", "keys", "values", "self", "this", "super", "async", "await", "yield", "from", "import", "new",
}


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_KEYWORDS = _NOT_FUNCTIONS | {
    "const", "function", "require", "module", "exports", "true", "false", "null", "undefined", "none", "else",
    "class", "static", "public", "private", "export", "default", "var", "let", "def", "then", "end", "case",
    "break", "continue", "throw", "try", "finally", "typeof", "void", "string", "number", "object", "args",
}


def identifiers(text: str, limit: int = 8) -> list[str]:
    """Distinctive identifiers in `text` (variable / function / config-key names), in order of appearance."""
    out: dict[str, None] = {}
    for m in _IDENT.finditer(text):
        w = m.group(0)
        if w.lower() not in _KEYWORDS:
            out.setdefault(w, None)
    return list(out)[:limit]


def called_names(text: str) -> list[str]:
    """Function names called in `text`, in order of first appearance, without common builtins."""
    out: dict[str, None] = {}
    for m in _CALL.finditer(text):
        name = m.group(1)
        if name.lower() not in _NOT_FUNCTIONS:
            out.setdefault(name, None)
    return list(out)


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out
