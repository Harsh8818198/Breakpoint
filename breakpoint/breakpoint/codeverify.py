"""Check every finding against the real source code before it can appear in a report.

A finding survives only if:
  1. a reviewer model points at the vulnerable lines AND those lines are found, verbatim and as live
     (non-comment) code, in the file it names -- a mechanical check, not a model's opinion;
  2. the claimed impact actually follows from that code;
  3. a second "defender" pass that reads the whole confirming file (and the functions it calls) cannot
     quote a protection that is enforced where the attacker's request is handled.

A claim the reviewer refutes gets one appeal, so a real bug is not lost to a protection that is only
rendered, only defined, or only commented out. A claim recovered on appeal still has to pass step 3.

Everything else is dropped and recorded with a reason code, so a run can show "17 claims checked, 0 held
up" instead of silently reporting guesses. The same verifier plugs into `simulate(..., verifier=...)`, so
refuted claims are fed back to the next generation together with the code that disproved them.
"""

from __future__ import annotations

import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import prompts
from .codeindex import CodeIndex, identifiers
from .coderetrieval import file_weight
from .llm import LLMFatalError, extract_json
from .models import Finding

CONFIRMED, REFUTED, UNVERIFIED, ERROR = "CONFIRMED", "REFUTED", "UNVERIFIED", "ERROR"

# Why a claim ended where it did (shown in the report's "rejected" section and the JSON).
CODE_LABELS = {
    "confirmed": "vulnerable code quoted, impact follows, no enforced defence found",
    "confirmed_on_appeal": "refuted at first, then shown real on appeal",
    "confirmed_absent": "the protection is missing: no live code uses it, and commented-out copies show it was switched off",
    "no_related_files": "no file in the repository relates to the claim",
    "judge_unverifiable": "the relevant code was not available to the reviewer",
    "invalid_verdict": "the reviewer gave no usable verdict",
    "quote_not_in_code": "the reviewer's quotes do not exist in the files named",
    "quote_is_comment": "the reviewer's quotes are comments, not live code",
    "impact_not_established": "reviewer did not establish that the claimed impact follows",
    "impact_does_not_follow": "the code does this, but the claimed harm does not follow from it",
    "contradicted_by_code": "the code contradicts the claim or already contains the protection",
    "defence_found": "a protection enforced in the code defeats the claim",
    "error": "the check itself failed",
}

_QUOTED = re.compile("`([^`\\n]{3,50})`|'([^'\\n]{3,50})'|\"([^\"\\n]{3,50})\"")
_CODEISH = re.compile(r"\b(?:[A-Za-z]+_[A-Za-z0-9_]+|[a-z]+[A-Z][A-Za-z0-9]+|[A-Za-z0-9_\-]+\.[a-z]{2,4})\b")
_ROUTE = re.compile(r"(?<![\w./])/[A-Za-z][\w\-./:]{2,40}")
DEFENDER_CHARS = 80000     # the defender reads each confirming file in full: this is what catches a check far from the flaw
_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "user", "users", "application", "app"}


_CODE_EXTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".py", ".rb", ".java", ".go", ".php", ".cs", ".rs", ".kt",
              ".scala", ".swift")
_IMPORT_START = re.compile(r"^\s*(?:const|let|var|import|from)\b")


def _import_only(line: str, name: str) -> bool:
    """A line that only imports `name` (`const helmet = require("helmet")`, `import bcrypt`) and never calls it."""
    return bool(_IMPORT_START.match(line)) and not re.search(r"(?<![A-Za-z0-9_$])" + re.escape(name) + r"\s*\(", line)


def _step_list(f: Finding) -> list[str]:
    s = f.steps_to_exploit
    if isinstance(s, str):
        return [s]
    return [str(x) for x in (s or [])]


def claim_terms(f: Finding, limit: int = 12) -> list[str]:
    """Code-looking words the claim itself mentions: quoted names, snake_case, camelCase, file names, routes."""
    text = " ".join([f.title, f.description, " ".join(_step_list(f))])
    seen: dict[str, None] = {}
    for m in _QUOTED.finditer(text):
        t = next(g for g in m.groups() if g)
        if t.lower() not in _STOP:
            seen.setdefault(t.strip(), None)
    for m in _CODEISH.finditer(text):
        seen.setdefault(m.group(0), None)
    for m in _ROUTE.finditer(text):                 # URL routes such as /learn or /allocations/:userId
        seen.setdefault(m.group(0).rstrip(".,;:"), None)
    return list(seen)[:limit]


def _steps(f: Finding) -> str:
    return " | ".join(_step_list(f))[:1200]


def _loads(raw: str) -> dict:
    d = extract_json(raw)
    if not isinstance(d, dict):
        raise ValueError("model did not return a JSON object")
    return d


def _result(status: str, code: str, reasoning: str = "", evidence: list[dict] | None = None) -> dict[str, Any]:
    return {"status": status, "code": code, "reasoning": reasoning, "evidence": evidence or []}


class CodeVerifier:
    """Callable with the `simulate(verifier=...)` contract: list[Finding] -> [{"ok", "evidence", ...}]."""

    def __init__(self, index: CodeIndex, llm, *, defend: bool = True, appeal: bool = True,
                 context_chars: int = 40000, max_files: int = 9, log=print, trace: bool = False):
        self.index, self.llm, self.defend, self.appeal = index, llm, defend, appeal
        self.context_chars, self.max_files, self.log = context_chars, max_files, log
        self.trace = trace                  # keep each claim's step-by-step trace in the results and records (it is always built)
        self.records: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ public
    def __call__(self, findings: list[Finding]) -> list[dict[str, Any]]:
        workers = max(1, min(getattr(self.llm, "max_workers", 1), len(findings)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(self.check, findings))
        out = []
        for f, r in zip(findings, results):
            rec = self._record(f, r)
            item = {"ok": r["status"] == CONFIRMED, "evidence": self._feedback(r), "status": r["status"],
                    "code": r["code"], "evidence_items": r["evidence"]}
            if self.trace:
                rec["trace"] = item["trace"] = r.get("trace") or []
            self.records.append(rec)
            out.append(item)
        return out

    def stats(self) -> dict[str, Any]:
        n = lambda s: sum(1 for r in self.records if r["status"] == s)  # noqa: E731
        return {"mode": "source-code", "files_indexed": len(self.index), "checked": len(self.records),
                "confirmed": n(CONFIRMED), "refuted": n(REFUTED), "unverified": n(UNVERIFIED),
                "errors": n(ERROR), "defender_pass": self.defend, "appeal_pass": self.appeal,
                "rejected": [r for r in self.records if r["status"] != CONFIRMED]}

    # ------------------------------------------------------------------ one finding
    def check(self, f: Finding) -> dict[str, Any]:
        """Check one claim. The result carries `trace`: every step taken, in order, with what each one saw and decided."""
        tr: list[dict[str, Any]] = []
        try:
            res = self._check(f, tr)
        except LLMFatalError:
            raise                      # no credit / bad key: stop the run, do not file it as one bad answer
        except Exception as e:  # noqa: BLE001 - one bad model reply must not sink the whole run
            print(f"[warn] could not verify {f.title!r}: {type(e).__name__}: {e}", file=sys.stderr)
            tr.append({"step": "error", "message": f"{type(e).__name__}: {e}"[:300]})
            res = _result(ERROR, "error", f"{type(e).__name__}: {e}")
        tr.append({"step": "decision", "status": res["status"], "code": res["code"], "why": CODE_LABELS.get(res["code"], res["code"])})
        res["trace"] = tr
        return res

    def _check(self, f: Finding, tr: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        tr = [] if tr is None else tr
        terms = claim_terms(f)
        located = self._locate(f, terms)
        files = [p for p in (self.index.resolve_path(x) for x in located.get("files", [])) if p]
        tr.append({"step": "locate", "files": list(files), "search_terms": [t for t in located.get("search_terms", []) if isinstance(t, str)][:8],
                   "note": "" if located else "the locating step gave nothing; the claim's own words were used"})
        # Files the agent cited are only a hint about what to put in front of the judge. They prove nothing: the judge
        # must still quote live vulnerable lines, the quotes are still checked against the files, and the defender still runs.
        for ref in getattr(f, "code_refs", None) or []:
            p = self.index.resolve_path(ref.get("file", "")) if isinstance(ref, dict) else None
            if p and p not in files:
                files.append(p)
        terms += [t for t in located.get("search_terms", []) if isinstance(t, str)]
        ranked = self.index.rank_files(terms, preferred=files, limit=self.max_files)
        tr.append({"step": "read", "files": [p for p, _ in ranked], "note": "files put in front of the judge"})
        if not ranked:
            return _result(UNVERIFIED, "no_related_files", "no file in the repository relates to this claim")

        judged = self._judge(f, self._context(ranked, self.context_chars, terms=terms))
        tr.append(self._judge_step(judged))
        res = self._decide(judged, tr)
        if res["code"] == "judge_unverifiable":
            # The reviewer can say what it needed to see; fetch exactly that and let it look once more.
            second = self._look_again(f, judged, ranked, terms)
            if second:
                tr.append({"step": "look_again", "asked_for": [t for t in (judged.get("need_to_see") or []) if isinstance(t, str)][:5]})
                tr.append(self._judge_step(second, "judge (second look)"))
                judged = second
            res = self._decide(judged, tr)
        res["_judged"] = judged

        if res["status"] == REFUTED and res["code"] == "contradicted_by_code" and self.appeal:
            res = self._on_appeal(f, res, terms, tr)
        if res["status"] == CONFIRMED and self.defend:
            res = self._defence_gate(f, res, terms, tr)
        res.pop("_judged", None)
        return res

    @staticmethod
    def _judge_step(judged: dict, label: str = "judge") -> dict[str, Any]:
        quotes = [{"file": str(e.get("file", "")), "quote": " ".join(str(e.get("quote", "")).split())[:240]}
                  for e in (judged.get("evidence") or [])[:4] if isinstance(e, dict)]
        return {"step": label, "verdict": str(judged.get("verdict", "")).strip().upper(), "impact_follows": judged.get("impact_follows"),
                "reasoning": str(judged.get("reasoning", ""))[:600], "attacker_needs": str(judged.get("attacker_needs", ""))[:200],
                "exploit_path": str(judged.get("exploit_path", ""))[:300], "quotes": quotes,
                "absent_names": [n for n in (judged.get("absent_names") or []) if isinstance(n, str)][:5]}

    def _look_again(self, f: Finding, judged: dict, ranked: list[tuple[str, list[int]]], terms: list[str]) -> dict | None:
        need = [t.strip() for t in (judged.get("need_to_see") or []) if isinstance(t, str) and len(t.strip()) >= 3][:5]
        if not need:
            return None
        try:
            wanted = dict(self.index.rank_files(need + terms, limit=self.max_files + 3))
            for name in need:                       # a name the reviewer asked for: show where it is defined
                for path, line in self.index.find_definitions(name):
                    wanted[path] = sorted(set(wanted.get(path, [])) | {line})
            merged = list(wanted.items()) + [(p, h) for p, h in ranked if p not in wanted]
            return self._judge(f, self._context(merged, int(self.context_chars * 1.5), terms=need + terms))
        except LLMFatalError:
            raise
        except Exception as e:  # noqa: BLE001 - a failed second look leaves the first answer in place
            print(f"[warn] second look failed for {f.title!r}: {type(e).__name__}: {e}", file=sys.stderr)
            return None

    # ------------------------------------------------------------------ deciding from a reviewer's reply
    def _decide(self, judged: dict, tr: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        reasoning = str(judged.get("reasoning", ""))[:600]
        verdict = str(judged.get("verdict", "")).strip().upper()
        if verdict == "UNVERIFIABLE":
            return _result(UNVERIFIED, "judge_unverifiable", reasoning)
        if verdict not in (CONFIRMED, REFUTED):
            return _result(UNVERIFIED, "invalid_verdict", reasoning)
        checked: list[dict[str, Any]] = []
        evidence, dropped = self._valid_evidence(judged.get("evidence"), checked)
        if tr is not None:
            tr.append({"step": "mechanical", "quotes": checked,
                       "note": "each quote must exist in the file it names, as live code (not a comment)"})
        absent = None
        if not evidence and verdict == CONFIRMED:
            # "This protection is missing / switched off" cannot be quoted: there is no live line to copy. Prove it by
            # search instead: the names the protection would carry appear in no live code, and the commented-out
            # copies the search finds are the evidence.
            absent = self._absence(judged.get("absent_names"))
            names = [n for n in (judged.get("absent_names") or []) if isinstance(n, str)][:5]
            if tr is not None and names:
                tr.append({"step": "absence_search", "names": names, "proved": bool(absent),
                           "switched_off_at": [f"{e['file']}:{e['line']}" for e in (absent or {}).get("evidence", [])]})
            if absent:
                evidence = absent["evidence"]
                reasoning = (reasoning + " [No live code uses " + ", ".join(f"`{n}`" for n in absent["names"])
                             + "; switched off at " + ", ".join(f"{e['file']}:{e['line']}" for e in evidence) + ".]")[:900]
        if not evidence:            # a verdict with no real quote behind it is not evidence
            code = "quote_is_comment" if dropped["comment"] and not dropped["not_found"] else "quote_not_in_code"
            return _result(UNVERIFIED, code, reasoning)
        if verdict == REFUTED:
            return _result(REFUTED, "contradicted_by_code", reasoning, evidence)
        # CONFIRMED: the behaviour being in the code is not enough, the promised harm must follow from it.
        follows = judged.get("impact_follows")
        if follows is False:
            return _result(REFUTED, "impact_does_not_follow",
                           "The code does this, but the claimed impact does not follow: " + reasoning, evidence)
        if follows is not True:
            return _result(UNVERIFIED, "impact_not_established", reasoning)
        return _result(CONFIRMED, "confirmed_absent" if absent else "confirmed", reasoning, evidence)

    def _absence(self, names) -> dict[str, Any] | None:
        """Mechanical proof that a protection is absent from live code, or None if it cannot be proved.

        `names` are literals the protection would carry (`httpOnly`, `csrf`, `helmet`). The whole repository is searched,
        whole words only. If ANY live line of a code file uses one of them, the claim has to be proved from that code, not
        from absence, so this returns None. Hits in docs, tests, manifests and templates neither enforce nor switch off
        anything and are ignored, and so is a bare `require`/`import` line (an import enforces nothing; a use shows up
        as its own live line). At least one commented-out line must exist, so there is something real to point at."""
        clean: list[str] = []
        for n in names if isinstance(names, list) else []:
            if isinstance(n, str) and re.fullmatch(r"[A-Za-z_$][\w$.\-]{2,39}", n.strip()):
                clean.append(n.strip())
        clean = list(dict.fromkeys(clean))[:5]
        if not clean:
            return None
        off: list[tuple[str, int, str]] = []
        for name in clean:
            for path, line, is_comment in self.index.find_word(name):
                if not path.lower().endswith(_CODE_EXTS) or file_weight(path) < 0.5:
                    continue
                if is_comment:
                    off.append((path, line, name))
                elif not _import_only(self.index.lines(path)[line - 1], name):
                    return None
        if not off:
            return None
        once: dict[tuple[str, int], str] = {}
        for p, ln, n in off:                                  # one item per line; the first name that hit it is kept
            once.setdefault((p, ln), n)
        items = [{"file": p, "line": ln, "quote": " ".join(self.index.lines(p)[ln - 1].split())[:240],
                  "kind": "switched_off", "absent": n} for (p, ln), n in list(once.items())[:3]]
        return {"names": clean, "evidence": items}

    def _valid_evidence(self, items, report: list | None = None) -> tuple[list[dict], dict[str, int]]:
        """Keep only quotes that exist in the file named AND are live code (a commented-out line is neither
        a flaw nor a defence). Each kept item carries its true line number, not the model's.
        If `report` is given, what happened to every quote is appended to it, for the trace."""
        valid: list[dict] = []
        dropped = {"not_found": 0, "comment": 0}
        for item in (items or [])[:4]:
            if not isinstance(item, dict):
                continue
            path = self.index.resolve_path(item.get("file", ""))
            quote = item.get("quote", "")
            near = item.get("start_line") if isinstance(item.get("start_line"), int) else None
            line = self.index.find_quote(path, quote, near=near) if path else None
            if line is None:
                dropped["not_found"] += 1
                outcome = "quote not found in the file" if path else "no such file in the repository"
            elif self.index.span_is_comment(path, line, quote):
                dropped["comment"] += 1
                outcome = "found, but it is a comment, not live code"
            else:
                valid.append({"file": path, "line": line, "quote": " ".join(str(quote).split())[:240]})
                outcome = "found, live code"
            if report is not None:
                report.append({"file": path or str(item.get("file", "")), "line": line, "quote": " ".join(str(quote).split())[:240],
                               "result": outcome})
        return valid, dropped

    # ------------------------------------------------------------------ appeal of a refutation
    def _on_appeal(self, f: Finding, res: dict, terms: list[str], tr: list[dict[str, Any]] | None = None) -> dict:
        """A refutation is only as good as the code it cites. Re-read that code with everything it refers to."""
        step: dict[str, Any] = {"step": "appeal", "refutation_cited": [f"{e['file']}:{e['line']}  {e['quote'][:100]}" for e in res["evidence"]][:3]}
        if tr is not None:
            tr.append(step)
        try:
            quotes = "\n".join(e["quote"] for e in res["evidence"])
            idents = identifiers(quotes)
            files = [e["file"] for e in res["evidence"]]
            ranked = dict(self.index.rank_files(idents + terms, preferred=files, limit=self.max_files + 2))
            for path, lines in self.index.callee_hits(self._around(res["evidence"])).items():
                ranked[path] = sorted(set(ranked.get(path, [])) | set(lines))
            ctx = self._context(list(ranked.items()), DEFENDER_CHARS, whole=files, terms=idents + terms)
            cited = "\n".join(f"{e['file']}:{e['line']}  {e['quote']}" for e in res["evidence"])
            reply = _loads(self.llm.complete(
                prompts.VERIFY_APPEAL_SYSTEM,
                prompts.VERIFY_APPEAL_USER.format(
                    title=f.title, description=f.description[:1500], steps=_steps(f), impact=f.impact[:500],
                    reasoning=res["reasoning"] or "(none given)", cited=cited, excerpts=ctx),
                task="verify_appeal", max_tokens=self.llm.scale_tokens(900)))
        except LLMFatalError:
            raise
        except Exception as e:  # noqa: BLE001 - an appeal that fails leaves the refutation standing
            print(f"[warn] appeal failed for {f.title!r}: {type(e).__name__}: {e}", file=sys.stderr)
            step.update(error=f"{type(e).__name__}: {e}"[:200], outcome="the appeal failed; the refutation stands")
            return res
        step.update(refutation_holds=reply.get("refutation_holds"), impact_follows=reply.get("impact_follows"),
                    reasoning=str(reply.get("reasoning", ""))[:600])
        if reply.get("refutation_holds") is not False or reply.get("impact_follows") is not True:
            step["outcome"] = "the refutation holds"
            return res
        appeal_quotes: list[dict[str, Any]] = []
        evidence, _ = self._valid_evidence(reply.get("evidence"), appeal_quotes)
        step["quotes"] = appeal_quotes
        if not evidence:
            step["outcome"] = "the appeal quoted no real vulnerable code; the refutation stands"
            return res
        step["outcome"] = "overturned: the vulnerable code is live and the cited defence does not enforce anything"
        out = _result(CONFIRMED, "confirmed_on_appeal", str(reply.get("reasoning", ""))[:600], evidence)
        out["_judged"] = {"exploit_path": reply.get("exploit_path", ""),
                          "defense_search_terms": reply.get("defense_search_terms", [])}
        return out

    # ------------------------------------------------------------------ the defender gate
    def _defence_gate(self, f: Finding, res: dict, terms: list[str], tr: list[dict[str, Any]] | None = None) -> dict:
        """Independent second look at every confirmation: the defender reads each confirming file whole, plus
        wherever the reviewer said a protection would live. This is the pass that catches 'the check is far away'."""
        judged = res.get("_judged", {})
        evidence = res["evidence"]
        confirming = [e["file"] for e in evidence]
        extra = [t for t in list(judged.get("defense_search_terms") or []) + list(judged.get("absent_names") or [])
                 if isinstance(t, str)]
        ranked = dict(self.index.rank_files(extra + terms, preferred=confirming, limit=self.max_files + 2))
        # A quoted call site says nothing about the callee: also show what the called functions really do.
        for path, lines in self.index.callee_hits(self._around(evidence)).items():
            ranked[path] = sorted(set(ranked.get(path, [])) | set(lines))
        case = (res["reasoning"] + " " + str(judged.get("exploit_path", ""))[:500]).strip()
        verdict = self._defend(f, case, self._context(list(ranked.items()), DEFENDER_CHARS, whole=confirming,
                                                       terms=extra + terms))
        step: dict[str, Any] = {"step": "defend", "files_read": list(ranked)[:8], "defence_found": verdict.get("defence_found"),
                                "reasoning": str(verdict.get("reasoning", ""))[:600], "outcome": "no protection found: the claim stands"}
        if tr is not None:
            tr.append(step)
        if verdict.get("defence_found") is True:
            defence_quotes: list[dict[str, Any]] = []
            defence, _ = self._valid_evidence(verdict.get("evidence"), defence_quotes)
            step["quotes"] = defence_quotes
            if defence:             # a defence only counts if it is real, live code that can be quoted
                step["outcome"] = "defeated: a protection is enforced in live code"
                return _result(REFUTED, "defence_found",
                               "Defender found a protection: " + str(verdict.get("reasoning", ""))[:500], defence)
            step["outcome"] = "the defender claimed a protection but quoted no real live code, so the claim stands"
        return _result(CONFIRMED, res["code"], res["reasoning"], evidence)

    def _around(self, evidence: list[dict]) -> list[str]:
        return ["\n".join(self.index.lines(e["file"])[max(0, e["line"] - 2): e["line"] + 3]) for e in evidence]

    # ------------------------------------------------------------------ model calls
    def _locate(self, f: Finding, terms: list[str]) -> dict:
        try:
            return _loads(self.llm.complete(
                prompts.VERIFY_LOCATE_SYSTEM,
                prompts.VERIFY_LOCATE_USER.format(
                    title=f.title, description=f.description[:1500], steps=_steps(f),
                    file_list=self.index.file_listing(terms + [f.title])),
                task="verify_locate", max_tokens=self.llm.scale_tokens(600)))
        except LLMFatalError:
            raise
        except Exception as e:  # noqa: BLE001 - locating is only a hint; grep on the claim's own words still works
            print(f"[warn] locate step failed for {f.title!r}: {e}", file=sys.stderr)
            return {}

    def _judge(self, f: Finding, excerpts: str) -> dict:
        return _loads(self.llm.complete(
            prompts.VERIFY_JUDGE_SYSTEM,
            prompts.VERIFY_JUDGE_USER.format(
                title=f.title, category=f.attack_category or "unspecified", description=f.description[:1800],
                steps=_steps(f), impact=f.impact[:500], excerpts=excerpts),
            task="verify_judge", max_tokens=self.llm.scale_tokens(900)))

    def _defend(self, f: Finding, reasoning: str, excerpts: str) -> dict:
        return _loads(self.llm.complete(
            prompts.VERIFY_DEFEND_SYSTEM,
            prompts.VERIFY_DEFEND_USER.format(
                title=f.title, description=f.description[:1500], steps=_steps(f), impact=f.impact[:500],
                reasoning=reasoning or "(none given)", excerpts=excerpts),
            task="verify_defend", max_tokens=self.llm.scale_tokens(800)))

    # ------------------------------------------------------------------ context for the models
    def _search_summary(self, terms: list[str], limit: int = 10) -> str:
        """Literal repo-wide hit counts. Lets a reviewer judge 'there is no X' from a search, not from a guess."""
        rows, seen = [], set()
        for t in terms:
            t = t.strip()
            if len(t) < 4 or t.lower() in seen:
                continue
            seen.add(t.lower())
            hits = self.index.grep(t, max_per_file=1)
            where = ", ".join(f"{p}:{ls[0]}" for p, ls in list(hits.items())[:4])
            rows.append(f"  {t!r}: {len(hits)} file(s)" + (f" e.g. {where}" if where else ""))
            if len(rows) >= limit:
                break
        if not rows:
            return ""
        head = f"REPO-WIDE LITERAL SEARCH (case-insensitive, {len(self.index)} source files; secret files are excluded)"
        return head + "\n" + "\n".join(rows) + "\n\n"

    def _context(self, ranked: list[tuple[str, list[int]]], budget: int, whole: list[str] | None = None,
                 terms: list[str] | None = None) -> str:
        whole = set(whole or [])
        parts, used = [], 0
        for path, hits in ranked:
            text = self.index.excerpt(path, hits, whole_if_chars=60000 if path in whole else 24000,
                                      max_chars=min(60000 if path in whole else 16000, budget))
            if parts and used + len(text) > budget:
                continue
            parts.append(text)
            used += len(text)
        return self._search_summary(terms or []) + "\n\n".join(parts)

    # ------------------------------------------------------------------ reporting helpers
    @staticmethod
    def _feedback(r: dict) -> str:
        """Text fed back to the next generation's agents about a claim that did not hold."""
        head = {REFUTED: "REFUTED BY THE CODE", UNVERIFIED: "NOT CONFIRMED IN THE CODE", ERROR: "COULD NOT BE CHECKED"}.get(
            r["status"], "")
        quotes = "; ".join(f"{e['file']}:{e['line']} `{e['quote'][:120]}`" for e in r["evidence"][:2])
        return " ".join(x for x in (head + ":" if head else "", r.get("reasoning", ""), quotes) if x)

    @staticmethod
    def _record(f: Finding, r: dict) -> dict[str, Any]:
        return {"id": f.id, "title": f.title, "category": f.attack_category, "claim": f.description[:600],
                "status": r["status"], "code": r["code"], "why": CODE_LABELS.get(r["code"], r["code"]),
                "reasoning": r.get("reasoning", ""), "evidence": r["evidence"]}


def apply_result(f: Finding, r: dict[str, Any]) -> None:
    """Record a confirmed result on its finding: the evidence, and, when the stricter verifier ran, the exploit judgement and votes."""
    f.verification, f.evidence = CONFIRMED, r["evidence_items"]
    f.exploit, f.votes = r.get("exploit") or {}, r.get("votes") or {}


def verify_findings(findings: list[Finding], index: CodeIndex, llm, **kw) -> tuple[list[Finding], dict[str, Any]]:
    """Check an existing list of findings (e.g. loaded from a saved report). Returns (confirmed, stats)."""
    v = CodeVerifier(index, llm, **kw)
    kept = []
    for f, res in zip(findings, v(findings)):
        if res["ok"]:
            apply_result(f, res)
            kept.append(f)
    return kept, v.stats()
