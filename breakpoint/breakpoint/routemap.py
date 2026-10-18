"""Map an Express app into routes -> handlers -> the code they call. No model is called and no code is run.

Why this exists: a model shown a whole repository misses most of it, and a model shown a summary invents
protections that are not there. A *route* is a natural unit to review: it has one entry point, a known list of
protections in front of it (login check, admin check, ...), and a bounded amount of code behind it. This module
finds those units from the source text alone, so each can be handed to a reviewer with exactly the code that matters.

What it understands (Express, plain JavaScript / TypeScript, CommonJS or `import`):
  - `app.get/post/put/delete/patch/all(path, ...middleware, handler)` and `router.*`, with `app.use(path, router)` mounts
  - handlers written inline, or as `obj.method` where `obj = new SomeClass(db)` and `SomeClass` is `require`d
  - what each handler calls one or two hops down (`dao.method(...)`), found by following the same imports
  - protections that are *switched off*: a commented-out copy of the same route, or a commented-out `app.use(...)`
  - which routes read request input and which dangerous operations (eval, redirect, DB query, HTTP request, ...) they reach
What it does not understand: `app.route()` chains, dynamic `require`, routes built in loops, other frameworks. For those it
returns fewer routes, never invented ones; `RouteMap.framework` is None when no Express app was found at all.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import sys
from dataclasses import dataclass, field

from .codeindex import CodeIndex

JS_EXTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
_TEST_DIRS = {"test", "tests", "__tests__", "spec", "cypress", "e2e", "__mocks__"}
_METHODS = "get|post|put|delete|patch|all|head|options"
_IDENT = r"[A-Za-z_$][\w$]*"
_CHAIN = re.compile(rf"{_IDENT}(?:\.{_IDENT})*")


# --------------------------------------------------------------------------- reading JS without being fooled by comments
def _scrub(text: str) -> tuple[str, str]:
    """(no_comments, skeleton), both exactly as long as `text` with newlines kept, so offsets and line numbers agree.
    `no_comments` blanks comments. `skeleton` also blanks the inside of strings and regex literals, so a brace or a
    parenthesis inside a string can never confuse bracket matching."""
    n = len(text)
    nc, sk = list(text), list(text)

    def blank(buf: list[str], a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if buf[k] != "\n":
                buf[k] = " "

    i, last = 0, ""
    while i < n:
        c = text[i]
        d = text[i + 1] if i + 1 < n else ""
        if c == "/" and d == "/":
            j = text.find("\n", i)
            j = n if j == -1 else j
            blank(nc, i, j), blank(sk, i, j)
            i = j
        elif c == "/" and d == "*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            blank(nc, i, j), blank(sk, i, j)
            i = j
        elif c in "'\"`":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == c or (c != "`" and text[j] == "\n"):
                    break
                j += 1
            blank(sk, i + 1, j)
            i, last = j + 1, c
        elif c == "/" and (last == "" or last in "(,=:[!&|?{};+-*%<>~^"):
            j, in_class = i + 1, False                      # a regex literal: skip to its closing slash
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    in_class = True
                elif text[j] == "]":
                    in_class = False
                elif text[j] == "/" and not in_class:
                    break
                j += 1
            blank(sk, i + 1, j)
            i, last = j + 1, "/"
        else:
            if not c.isspace():
                last = c
            i += 1
    return "".join(nc), "".join(sk)


_PAIRS = {"(": ")", "{": "}", "[": "]"}
_CONTINUES = ("=>", "=", ",", "(", ".", "+", "&&", "||", "?", ":")      # a line ending like this continues on the next one


def _close_of(sk: str, i: int) -> int:
    """Index of the bracket that closes the one at `i` (of the same kind), or -1."""
    o, c, depth = sk[i], _PAIRS[sk[i]], 0
    for j in range(i, len(sk)):
        ch = sk[j]
        if ch == o:
            depth += 1
        elif ch == c:
            depth -= 1
            if depth == 0:
                return j
    return -1


def _split_args(sk: str, a: int, b: int) -> list[tuple[int, int]]:
    """Top-level comma-separated pieces of sk[a:b], as (start, end) offsets."""
    out, depth, start = [], 0, a
    for j in range(a, b):
        ch = sk[j]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append((start, j))
            start = j + 1
    if sk[start:b].strip():
        out.append((start, b))
    return out


class _Src:
    def __init__(self, path: str, lines: list[str]):
        self.path = path
        self.text = "\n".join(lines)
        self.nc, self.sk = _scrub(self.text)
        self.starts = [0] + [m.end() for m in re.finditer("\n", self.text)]
        self.n_lines = len(lines)

    def line(self, pos: int) -> int:
        return bisect.bisect_right(self.starts, pos)

    def lines_text(self, start: int, end: int) -> str:
        """Comment-free source of 1-based lines start..end."""
        a = self.starts[start - 1]
        b = self.starts[end] if end < len(self.starts) else len(self.nc)
        return self.nc[a:b]


# --------------------------------------------------------------------------- results
@dataclass(frozen=True)
class Span:
    file: str
    start: int           # 1-based, inclusive
    end: int
    name: str = ""

    def __repr__(self) -> str:
        return f"{self.name + ' ' if self.name else ''}{self.file}:{self.start}-{self.end}"

    def to_dict(self) -> dict:
        return {"name": self.name, "file": self.file, "start": self.start, "end": self.end}


@dataclass
class Route:
    method: str
    path: str                                   # full path including any router mount prefix
    file: str                                   # where it is registered
    line: int
    reg_end: int                                # last line of the registration statement
    middleware: list[dict] = field(default_factory=list)   # {"name", "span": Span|None, "line"}, in order
    handler: dict = field(default_factory=dict)             # {"name", "span": Span|None}
    callees: list[Span] = field(default_factory=list)       # code the handler reaches, nearest first
    reads_input: bool = False
    sinks: list[str] = field(default_factory=list)
    disabled_variants: list[dict] = field(default_factory=list)   # {"line", "text"}: commented-out copies of this route

    @property
    def id(self) -> str:
        return f"{self.method} {self.path} @{self.file}:{self.line}"

    @property
    def label(self) -> str:
        return f"{self.method} {self.path}"

    def spans(self) -> list[Span]:
        """Every region of source that belongs to this route's node."""
        out = [Span(self.file, self.line, self.reg_end, "registration")]
        out += [m["span"] for m in self.middleware if m.get("span")]
        if self.handler.get("span"):
            out.append(self.handler["span"])
        out += self.callees
        for v in self.disabled_variants:
            out.append(Span(self.file, v["line"], v["line"], "disabled variant"))
        return out

    def to_dict(self) -> dict:
        return {
            "id": self.id, "method": self.method, "path": self.path, "file": self.file, "line": self.line,
            "middleware": [{"name": m["name"], "span": m["span"].to_dict() if m.get("span") else None} for m in self.middleware],
            "handler": {"name": self.handler.get("name", ""), "span": self.handler["span"].to_dict() if self.handler.get("span") else None},
            "callees": [c.to_dict() for c in self.callees],
            "reads_input": self.reads_input, "sinks": self.sinks, "disabled_variants": self.disabled_variants,
        }


@dataclass
class RouteMap:
    root: str
    framework: str | None = None                 # "express" or None
    entry_file: str | None = None
    routes: list[Route] = field(default_factory=list)
    app_level: list[Span] = field(default_factory=list)          # code that affects every route (entry file, config/)
    global_middleware: list[dict] = field(default_factory=list)  # {"expr", "line", "active"}; active False = commented out
    unresolved: list[str] = field(default_factory=list)          # names that could not be followed (usually library code)

    def to_dict(self) -> dict:
        return {
            "framework": self.framework, "entry_file": self.entry_file,
            "routes": [r.to_dict() for r in self.routes],
            "app_level": [s.to_dict() for s in self.app_level],
            "global_middleware": self.global_middleware, "unresolved": self.unresolved,
        }

    def node_source(self, route: Route, index: CodeIndex, max_chars: int = 16000) -> str:
        """The code a reviewer of this route should read, as numbered source: registration, the protections in
        front of it, the handler, and what the handler calls. Routes sharing a file share one `### file` block."""
        by_file: dict[str, list[tuple[int, int]]] = {}
        for s in route.spans():
            by_file.setdefault(s.file, []).append((s.start, s.end))
        parts, used = [], 0
        for path in sorted(by_file, key=lambda p: (p != route.file, p)):
            if not index.has(path):
                continue
            text = index.render_ranges(path, by_file[path], limit=max(2000, max_chars - used))
            parts.append(text)
            used += len(text)
        return "\n\n".join(parts)


# --------------------------------------------------------------------------- resolving names to code
_SINKS = {
    "eval": r"\beval\s*\(|new\s+Function\s*\(|\bvm\.run\w*\s*\(",
    "shell": r"\bchild_process\b|(?<![.\w$])(?:exec|execSync|spawn|spawnSync)\s*\(",
    "redirect": r"\.redirect\s*\(",
    "http_request": r"\bneedle\.|\baxios\b|(?<![.\w$])(?:fetch|request|got)\s*\(|\bhttps?\.(?:get|request)\s*\(",
    "db_query": r"\$where|\.(?:find|findOne|findById|update|updateOne|updateMany|insert|insertOne|insertMany|remove|deleteOne|deleteMany|aggregate|query)\s*\(",
    "file_access": r"\bfs\.\w+|\breadFile\w*\s*\(|\bsendFile\s*\(|\bcreateReadStream\s*\(",
    "response_write": r"\bres\.(?:send|write|end|json|render)\s*\(",
    "session_use": r"\breq\.session\b",
    "credentials": r"\bpassword\b|\bbcrypt\b|\bcrypto\.\w+",
}
_SINK_RX = {k: re.compile(v) for k, v in _SINKS.items()}
_INPUT = re.compile(r"\breq\.(?:body|query|params|headers|cookies|files|file)\b|\brequest\.(?:body|query|params)\b")
_NOT_CALLS = {"if", "for", "while", "switch", "catch", "function", "return", "typeof", "require", "super", "console",
              "async", "await", "new", "import", "constructor", "Number", "String", "Boolean", "parseInt", "parseFloat",
              "JSON", "Math", "Object", "Array", "Date", "Promise", "next", "done", "callback", "cb"}


class _Repo:
    def __init__(self, index: CodeIndex):
        self.index = index
        self._src: dict[str, _Src] = {}
        self._imports: dict[str, dict[str, tuple[str, str | None]]] = {}
        self._instances: dict[str, dict[str, str]] = {}
        self._aliases: dict[str, dict[str, str]] = {}
        self._defs: dict[tuple[str, str], tuple[Span | None, str | None]] = {}
        self.unresolved: set[str] = set()

    def src(self, path: str) -> _Src:
        s = self._src.get(path)
        if s is None:
            s = self._src[path] = _Src(path, self.index.lines(path))
        return s

    # ---- imports, `new X(...)` instances, `const a = b.c` aliases
    def module_file(self, from_file: str, spec: str) -> str | None:
        if not spec.startswith("."):
            return None                                       # a package, not our code
        base = os.path.normpath(os.path.join(os.path.dirname(from_file), spec)).replace("\\", "/")
        for cand in [base] + [base + e for e in JS_EXTS] + [f"{base}/index{e}" for e in JS_EXTS]:
            if self.index.has(cand):
                return cand
        return None

    def imports(self, path: str) -> dict[str, tuple[str, str | None]]:
        """local name -> (module spec, property or None)."""
        cached = self._imports.get(path)
        if cached is not None:
            return cached
        nc, out = self.src(path).nc, {}
        for m in re.finditer(rf"(?:const|let|var)\s+({_IDENT})\s*=\s*require\(\s*([\"'])([^\"']+)\2\s*\)(?:\.({_IDENT}))?", nc):
            out[m.group(1)] = (m.group(3), m.group(4))
        for m in re.finditer(r"(?:const|let|var)\s*\{([^}]*)\}\s*=\s*require\(\s*([\"'])([^\"']+)\2\s*\)", nc):
            for part in m.group(1).split(","):
                bits = [b.strip() for b in part.split(":")]
                if bits and re.fullmatch(_IDENT, bits[0] or ""):
                    out[bits[-1] if re.fullmatch(_IDENT, bits[-1]) else bits[0]] = (m.group(3), bits[0])
        for m in re.finditer(rf"import\s+({_IDENT})\s+from\s+([\"'])([^\"']+)\2", nc):
            out[m.group(1)] = (m.group(3), None)
        for m in re.finditer(r"import\s*\{([^}]*)\}\s*from\s+([\"'])([^\"']+)\2", nc):
            for part in m.group(1).split(","):
                bits = [b.strip() for b in re.split(r"\s+as\s+", part.strip())]
                if bits and re.fullmatch(_IDENT, bits[0] or ""):
                    out[bits[-1]] = (m.group(3), bits[0])
        for m in re.finditer(rf"import\s*\*\s*as\s+({_IDENT})\s+from\s+([\"'])([^\"']+)\2", nc):      # import * as utils from ...
            out[m.group(1)] = (m.group(3), None)
        self._imports[path] = out
        return out

    def instances(self, path: str) -> dict[str, str]:
        cached = self._instances.get(path)
        if cached is None:
            cached = self._instances[path] = {
                m.group(1): m.group(2)
                for m in re.finditer(rf"(?:const|let|var)\s+({_IDENT})\s*=\s*new\s+({_IDENT})\s*\(", self.src(path).nc)}
        return cached

    def aliases(self, path: str) -> dict[str, str]:
        cached = self._aliases.get(path)
        if cached is None:
            cached = self._aliases[path] = {
                m.group(1): m.group(2)
                for m in re.finditer(rf"(?:const|let|var)\s+({_IDENT})\s*=\s*({_IDENT}(?:\.{_IDENT})+)\s*;", self.src(path).nc)}
        return cached

    # ---- where a name is defined
    def find_def(self, path: str, name: str) -> tuple[Span | None, str | None]:
        """(span of the definition, None) or (None, alias target) or (None, None). Looks for `this.name =`,
        `exports.name =`, `function name(`, `const name =`, `name: function`, and method shorthand."""
        key = (path, name)
        if key in self._defs:
            return self._defs[key]
        s, n = self.src(path), re.escape(name)
        patterns = [
            rf"(?m)^[ \t]*(?:this|exports|module\.exports|self)\.{n}\s*=",
            rf"(?m)^[ \t]*(?:export\s+)?(?:async\s+)?function\s*\*?\s+{n}\s*\(",
            rf"(?m)^[ \t]*(?:export\s+)?(?:const|let|var)\s+{n}\s*=(?!\s*(?:require\(|new\s))",
            rf"(?m)^[ \t]*{n}\s*:\s*(?:async\s*)?(?:function\b|\()",
            rf"(?m)^[ \t]*(?:async\s+|static\s+)*{n}\s*\([^)\n]*\)\s*\{{",
        ]
        result: tuple[Span | None, str | None] = (None, None)
        for pat in patterns:
            m = re.search(pat, s.nc)
            if not m:
                continue
            result = self._span_from(s, name, m.start(), m.end())
            if result != (None, None):
                break
        self._defs[key] = result
        return result

    def _span_from(self, s: _Src, name: str, start: int, after: int) -> tuple[Span | None, str | None]:
        first = s.line(start)
        # the body is the first {...} after the match, unless a ';' ends the statement first
        j, brace, semi = after, -1, -1
        paren = 0
        while j < len(s.sk):
            ch = s.sk[j]
            if ch == "(":
                paren += 1
            elif ch == ")":
                paren -= 1
            elif paren <= 0 and ch == "{":
                brace = j
                break
            elif paren <= 0 and ch == ";":
                semi = j
                break
            elif paren <= 0 and ch == "\n" and s.nc[after:j].strip() and not s.nc[after:j].rstrip().endswith(_CONTINUES):
                semi = j                          # no semicolon (TypeScript style): the statement ends with its line
                break
            j += 1
        if brace == -1 and semi == -1 and s.nc[after:].strip():
            semi = len(s.sk)                      # the statement is the last thing in the file and has no semicolon
        if brace != -1:
            end = _close_of(s.sk, brace)
            if end == -1:
                return None, None
            return Span(s.path, first, s.line(end), name), None
        if semi != -1:
            rhs = s.nc[after:semi].strip()
            if _CHAIN.fullmatch(rhs):
                return None, rhs                                # `this.x = sessionHandler.y;` -- an alias
            return Span(s.path, first, s.line(semi), name), None
        return None, None

    # ---- following a dotted reference to its code
    def resolve(self, path: str, dotted: str, depth: int = 0) -> Span | None:
        if depth > 4 or not _CHAIN.fullmatch(dotted):
            return None
        parts = dotted.split(".")
        base, rest = parts[0], parts[1:]
        inst, imps = self.instances(path), self.imports(path)
        if base in inst and rest:
            cls = inst[base]
            target = self._class_file(path, cls)
            if target:
                return self._follow(target, rest[0], depth)
            return None
        if base in self.aliases(path) and base not in imps:
            return self.resolve(path, ".".join([self.aliases(path)[base]] + rest), depth + 1)
        if base in imps:
            spec, prop = imps[base]
            target = self.module_file(path, spec)
            if not target:
                return None
            name = rest[0] if rest else (prop or base)
            return self._follow(target, name, depth)
        if not rest:
            return self._follow(path, base, depth)
        return None

    def resolve_expr(self, path: str, text: str, depth: int = 0) -> Span | None:
        """A middleware or handler argument to the code behind it. Besides a plain name this follows the factory style
        (`login()`, `security.isAuthorized()`) and wrappers (`utils.asyncHandler(upload())`): arguments that are themselves
        calls are tried first, because the wrapper is rarely the interesting code, then the called function itself."""
        text = text.strip()
        if _CHAIN.fullmatch(text):
            return self.resolve(path, text)
        m = re.fullmatch(rf"({_IDENT}(?:\.{_IDENT})*)\s*\((.*)\)", text, re.S)
        if not m or depth > 3:
            return None
        inner = m.group(2)
        for a, b in _split_args(_scrub(inner)[1], 0, len(inner)):
            span = self.resolve_expr(path, inner[a:b], depth + 1)
            if span:
                return span
        return self.resolve(path, m.group(1))

    def _follow(self, path: str, name: str, depth: int) -> Span | None:
        span, alias = self.find_def(path, name)
        if span is None and alias:
            return self.resolve(path, alias, depth + 1)
        return span

    def _class_file(self, path: str, cls: str) -> str | None:
        spec = self.imports(path).get(cls)
        if spec:
            return self.module_file(path, spec[0])
        return path if self.find_def(path, cls)[0] else None

    # ---- what a span calls
    def callees(self, span: Span, limit: int = 12, depth: int = 2) -> list[Span]:
        out: list[Span] = []
        seen = {(span.file, span.start)}
        frontier = [span]
        for _ in range(depth):
            nxt: list[Span] = []
            for sp in frontier:
                s = self.src(sp.file)
                text = s.lines_text(sp.start, sp.end)
                inst = self.instances(sp.file)
                imps = self.imports(sp.file)
                for m in re.finditer(rf"(?<![.\w$])({_IDENT})\.({_IDENT})\s*\(", text):
                    if m.group(1) in inst or (m.group(1) in imps and imps[m.group(1)][0].startswith(".")):
                        self._add(sp.file, f"{m.group(1)}.{m.group(2)}", seen, out, nxt, limit)
                for m in re.finditer(rf"(?<![.\w$]){_IDENT}(?=\s*\()", text):
                    if m.group(0) not in _NOT_CALLS:
                        self._add(sp.file, m.group(0), seen, out, nxt, limit)
            frontier = nxt
        return out

    def _add(self, path: str, dotted: str, seen: set, out: list, nxt: list, limit: int) -> None:
        if len(out) >= limit:
            return
        target = self.resolve(path, dotted)
        if target is None or (target.file, target.start) in seen:
            return
        target = Span(target.file, target.start, target.end, dotted)
        seen.add((target.file, target.start))
        out.append(target)
        nxt.append(target)


# --------------------------------------------------------------------------- finding the routes
def _is_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    return any(p in _TEST_DIRS for p in parts[:-1]) or bool(re.search(r"\.(?:test|spec)\.\w+$", parts[-1]))


def _receivers(src: _Src) -> set[str]:
    names = {"app", "router"}
    for m in re.finditer(rf"(?:const|let|var)\s+({_IDENT})\s*=\s*(?:express\s*\(\s*\)|(?:express\.)?Router\s*\(|require\([^)]*\)\.Router\s*\()", src.nc):
        names.add(m.group(1))
    return names


_ROUTE_CALL = re.compile(rf"(?<![.\w$])({_IDENT})\.({_METHODS}|use)\s*\(")
_COMMENTED_ROUTE = re.compile(rf"(?<![.\w$])({_IDENT})\.({_METHODS})\s*\(\s*([\"'])([^\"']*)\3")


def _parse_call(src: _Src, open_paren: int) -> list[tuple[str, int, int]] | None:
    """The arguments of the call whose '(' is at `open_paren`: (comment-free text, start offset, end offset)."""
    close = _close_of(src.sk, open_paren)
    if close == -1:
        return None
    return [(src.nc[a:b].strip(), a, b) for a, b in _split_args(src.sk, open_paren + 1, close)]


def _is_inline(text: str) -> bool:
    return bool(re.match(r"(?:async\s+)?function\b", text)) or "=>" in text.split("{", 1)[0]


def map_routes(index: CodeIndex, max_routes: int = 400) -> RouteMap:
    repo = _Repo(index)
    js_files = [p for p in index.paths() if p.lower().endswith(JS_EXTS) and not _is_test_path(p)]
    result = RouteMap(root=index.root)

    # entry file: the one that creates the express app (prefer the one that also listens)
    entries = [p for p in js_files if re.search(r"\bexpress\s*\(\s*\)", repo.src(p).nc)]
    entries.sort(key=lambda p: (".listen(" not in repo.src(p).nc, p))
    if entries:
        result.framework, result.entry_file = "express", entries[0]

    # pass 1: router mounts (`app.use("/prefix", routerVar)`) -> which file mounts which, under what prefix
    mounts: dict[str, tuple[str, str]] = {}          # child file -> (parent file, prefix)
    registrations: list[tuple[str, re.Match]] = []
    for path in js_files:
        src = repo.src(path)
        recv = _receivers(src)
        for m in _ROUTE_CALL.finditer(src.nc):
            if m.group(1) not in recv:
                continue
            registrations.append((path, m))
            if m.group(2) != "use":
                continue
            args = _parse_call(src, m.end() - 1)
            if not args or len(args) < 2 or args[0][0][:1] not in ("'", '"', "`"):
                continue
            target = args[-1][0]
            if _CHAIN.fullmatch(target):
                span = repo.imports(path).get(target.split(".")[0])
                child = repo.module_file(path, span[0]) if span else None
                if child and child != path and child not in mounts:
                    mounts[child] = (path, args[0][0].strip("'\"`"))

    def prefix_of(path: str) -> str:
        pre, seen = "", {path}
        while path in mounts:
            parent, p = mounts[path]
            pre = p.rstrip("/") + pre
            if parent in seen:
                break
            seen.add(parent)
            path = parent
        return pre

    # pass 2: the routes themselves, and global middleware
    for path, m in registrations:
        src = repo.src(path)
        method = m.group(2)
        args = _parse_call(src, m.end() - 1)
        if args is None:
            continue
        line, close = src.line(m.start()), _close_of(src.sk, m.end() - 1)
        if method == "use":
            first = args[0][0] if args else ""
            has_path = first[:1] in ("'", '"', "`", "[", "/")
            rest = args[1:] if has_path else args
            if path == result.entry_file or not has_path:
                if rest and not (len(rest) == 1 and _CHAIN.fullmatch(rest[0][0]) and rest[0][0] in repo.imports(path)
                                 and (repo.module_file(path, repo.imports(path)[rest[0][0]][0]) or "") in mounts):
                    result.global_middleware.append({"expr": " ".join(rest[-1][0].split())[:120], "line": line, "active": True, "file": path})
            continue
        if len(args) < 2:                                    # `app.get("setting")` reads a setting, it is not a route
            continue
        raw_path = args[0][0]
        if raw_path[:1] not in ("'", '"', "`", "[", "/"):
            continue
        route_path = raw_path.strip("'\"`") if raw_path[:1] in ("'", '"', "`") else raw_path
        route = Route(method=method.upper(), path=prefix_of(path) + route_path, file=path, line=line, reg_end=src.line(close))
        *mw, last = args[1:]
        for text, a, b in mw:
            route.middleware.append(_ref(repo, path, src, text, a, b))
        h = _ref(repo, path, src, last[0], last[1], last[2])
        route.handler = {"name": h["name"], "span": h["span"]}
        if h["span"]:
            route.callees = repo.callees(h["span"])
        if h["name"] and not h["span"] and _CHAIN.fullmatch(h["name"]):
            result.unresolved.append(h["name"])
        code = "".join(repo.src(sp.file).lines_text(sp.start, sp.end) for sp in ([h["span"]] if h["span"] else []) + route.callees)
        route.reads_input = bool(_INPUT.search(code))
        route.sinks = [k for k, rx in _SINK_RX.items() if rx.search(code)]
        result.routes.append(route)
        if len(result.routes) >= max_routes:
            break
    result.unresolved = sorted(set(result.unresolved) | {m["name"] for r in result.routes for m in r.middleware
                                                          if m["name"] and not m.get("span") and _CHAIN.fullmatch(m["name"])})

    # protections that were switched off: a commented-out copy of a route, or of an app-level `use`
    for path in {r.file for r in result.routes} | ({result.entry_file} if result.entry_file else set()):
        src = repo.src(path)
        recv = _receivers(src)
        src_lines = src.text.split("\n")
        for m in _COMMENTED_ROUTE.finditer(src.text):
            if m.group(1) not in recv or src.nc[m.start():m.end()].strip():
                continue                                      # live code, not a comment
            ln = src.line(m.start())
            for r in result.routes:
                if r.file == path and r.method == m.group(2).upper() and r.path.endswith(m.group(4)) and ln != r.line:
                    r.disabled_variants.append({"line": ln, "text": src_lines[ln - 1].strip()[:200]})
        if path == result.entry_file:
            for m in re.finditer(rf"(?<![.\w$])({_IDENT})\.use\s*\(([^\n]*)", src.text):
                if m.group(1) in recv and not src.nc[m.start():m.end()].strip():
                    result.global_middleware.append({"expr": _use_expr(m.group(2)), "line": src.line(m.start()),
                                                     "active": False, "file": path})

    # code that affects every route
    if result.entry_file:
        result.app_level.append(Span(result.entry_file, 1, repo.src(result.entry_file).n_lines, "app entry"))
    for p in index.paths():
        if re.match(r"(?:.*/)?config/", p) and p.lower().endswith(JS_EXTS) and len(index.lines(p)) <= 500 and not _is_test_path(p):
            result.app_level.append(Span(p, 1, len(index.lines(p)), "config"))
    result.global_middleware.sort(key=lambda g: (g["file"], g["line"]))
    return result


def _use_expr(rest_of_line: str) -> str:
    """What was passed to `app.use(` on this line, without the closing `)` or a trailing `// comment`."""
    text, depth = rest_of_line, 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                text = text[:i]
                break
    return re.sub(r"\s*//.*$", "", text).strip()[:120]


def _ref(repo: _Repo, path: str, src: _Src, text: str, a: int, b: int) -> dict:
    """One middleware/handler argument: inline function, or a name we try to follow to its definition."""
    if _is_inline(text):
        lead = len(src.nc[a:b]) - len(src.nc[a:b].lstrip())
        return {"name": "<inline>", "span": Span(path, src.line(a + lead), src.line(max(a, b - 1)), "inline handler"),
                "line": src.line(a + lead)}
    name = " ".join(text.split())[:80]
    span = repo.resolve_expr(path, text)
    if span:
        span = Span(span.file, span.start, span.end, name)
    return {"name": name, "span": span, "line": src.line(a)}


# --------------------------------------------------------------------------- command line
def render(rm: RouteMap) -> str:
    if rm.framework is None:
        return "No Express app found (this mapper understands Express only)."
    out = [f"Express app, entry {rm.entry_file}: {len(rm.routes)} routes"]
    for r in rm.routes:
        mw = ", ".join(m["name"] for m in r.middleware) or "none"
        h = r.handler.get("span")
        out.append(f"\n{r.method:<6} {r.path}   [{r.file}:{r.line}]")
        out.append(f"   protections in front: {mw}" + ("" if all(m.get("span") for m in r.middleware) else "   (some not followed)"))
        out.append(f"   handler: {r.handler.get('name')}" + (f"  -> {h.file}:{h.start}-{h.end}" if h else "  (not found)"))
        if r.callees:
            out.append("   calls: " + "; ".join(f"{c.name or '?'} {c.file}:{c.start}-{c.end}" for c in r.callees))
        out.append(f"   reads request input: {'yes' if r.reads_input else 'no'}; reaches: {', '.join(r.sinks) or 'nothing notable'}")
        for v in r.disabled_variants:
            out.append(f"   SWITCHED OFF at line {v['line']}: {v['text']}")
    if rm.global_middleware:
        out.append("\napp-level middleware:")
        for g in rm.global_middleware:
            out.append(f"   {g['file']}:{g['line']} {'ACTIVE' if g['active'] else 'switched off'}: {g['expr']}")
    if rm.unresolved:
        out.append("\nnot followed (library or dynamic): " + ", ".join(rm.unresolved))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Map an Express app: routes, protections, handlers, what they call")
    ap.add_argument("path", help="local folder")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)
    rm = map_routes(CodeIndex.from_dir(args.path))
    print(json.dumps(rm.to_dict(), indent=2) if args.json else render(rm))


if __name__ == "__main__":
    main(sys.argv[1:])
