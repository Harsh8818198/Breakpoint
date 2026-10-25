"""The stricter verifier: each decision is repeated until a majority agrees, and a confirmed claim must also be exploitable.

Two things the first real-code measurement (`bench_runs/history_pilot/RESULTS.md`) showed the plain code check cannot do:

  - it is not stable. Run again on the same claim and the same code it changed its mind on 2 of 9 claims, including a true flaw
    that was kept once and refuted once. One run per claim is a coin that is biased, not a verdict;
  - "confirmed" means the code does what the claim says, not that it is a vulnerability: none of ten survivors was one.

`ProvenVerifier` runs the code check up to `checks` times per claim, stopping as soon as a majority agrees (2 identical answers
out of 3 end it, so most claims cost two runs, not three). A claim the majority confirms then goes to the exploitability judge
(`exploit.py`), voted the same way. The result carries how many runs agreed, so a finding can say "held in 3 of 3 checks" and a
borderline one can be seen to be borderline.

Statuses: CONFIRMED (a vulnerability), OBSERVATION (accurate about the code, not exploitable: kept in the stats with its reason,
left out of the report's findings), REFUTED, UNVERIFIED, ERROR. `checks=1, exploit=False` is the old single check.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .codeindex import CodeIndex
from .codeverify import CONFIRMED, ERROR, REFUTED, UNVERIFIED, CodeVerifier, _result
from .exploit import CONDITIONAL, EXPLOIT_LABELS, EXPLOITABLE, ExploitJudge
from .llm import LLMFatalError
from .models import Finding

OBSERVATION = "OBSERVATION"
DEFAULT_CHECKS = 3
_MAX_ERRORS = 2          # a reply that cannot be read is retried, but not for ever, and never counts as a vote


def vote(attempt: Callable[[], Any], is_yes: Callable[[Any], bool], is_error: Callable[[Any], bool], checks: int):
    """Call `attempt` until a majority of `checks` answers agree. Returns (answers, yes, no, errors).
    An error is not an answer. If the votes tie (an even `checks`), neither side has won and the caller treats it as 'no'."""
    need = checks // 2 + 1
    answers: list[Any] = []
    yes = no = errors = 0
    while yes < need and no < need and yes + no < checks and errors <= _MAX_ERRORS:
        r = attempt()
        if is_error(r):
            errors += 1
            continue
        answers.append(r)
        if is_yes(r):
            yes += 1
        else:
            no += 1
    return answers, yes, no, errors


def _most_common(items: list[tuple[str, str]]) -> tuple[str, str]:
    return Counter(items).most_common(1)[0][0]


class ProvenVerifier:
    """Same contract as `CodeVerifier` (list[Finding] -> [{"ok", "evidence", "status", "code", "evidence_items", ...}]), plus
    `votes` and `exploit` on a confirmed result."""

    def __init__(self, index: CodeIndex, llm, *, checks: int = DEFAULT_CHECKS, exploit: bool = True, defend: bool = True,
                 appeal: bool = True, log=print, **kw):
        if checks < 1:
            raise ValueError("checks must be at least 1")
        self.cv = CodeVerifier(index, llm, defend=defend, appeal=appeal, log=log, **kw)
        self.judge = ExploitJudge(self.cv) if exploit else None
        self.index, self.llm, self.checks, self.exploit, self.defend, self.appeal = index, llm, checks, exploit, defend, appeal
        self.records: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ public
    def __call__(self, findings: list[Finding]) -> list[dict[str, Any]]:
        workers = max(1, min(getattr(self.llm, "max_workers", 1), len(findings)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(self.check, findings))
        out = []
        for f, r in zip(findings, results):
            self.records.append(self._record(f, r))
            out.append({"ok": r["status"] == CONFIRMED, "evidence": self._feedback(r), "status": r["status"], "code": r["code"],
                        "evidence_items": r["evidence"], "exploit": r.get("exploit") or {}, "votes": r.get("votes") or {}})
        return out

    def stats(self) -> dict[str, Any]:
        n = lambda s: sum(1 for r in self.records if r["status"] == s)  # noqa: E731
        split = sum(1 for r in self.records if _split(r.get("votes") or {}))
        return {"mode": "source-code", "files_indexed": len(self.index), "checked": len(self.records),
                "confirmed": n(CONFIRMED), "observations": n(OBSERVATION), "refuted": n(REFUTED), "unverified": n(UNVERIFIED),
                "errors": n(ERROR), "defender_pass": self.defend, "appeal_pass": self.appeal,
                "checks": self.checks, "exploitability": self.exploit, "split_decisions": split,
                "rejected": [r for r in self.records if r["status"] != CONFIRMED]}

    # ------------------------------------------------------------------ one finding
    def check(self, f: Finding) -> dict[str, Any]:
        answers, yes, no, errors = vote(lambda: self.cv.check(f), lambda r: r["status"] == CONFIRMED,
                                        lambda r: r["status"] == ERROR, self.checks)
        votes: dict[str, Any] = {"code_check": {"confirmed": yes, "cast": yes + no, "errors": errors}}
        if not answers:
            return {**_result(ERROR, "error", "the check failed every time it was tried"), "votes": votes}
        if yes <= no:
            rejects = [r for r in answers if r["status"] != CONFIRMED]
            status, code = _most_common([(r["status"], r["code"]) for r in rejects])
            base = next(r for r in rejects if (r["status"], r["code"]) == (status, code))
            return {**base, "votes": votes}
        base = next(r for r in answers if r["status"] == CONFIRMED)
        if not self.judge:
            return {**base, "votes": votes}
        return self._exploitable(f, base, votes)

    def _exploitable(self, f: Finding, base: dict[str, Any], votes: dict[str, Any]) -> dict[str, Any]:
        positive = lambda r: r["tier"] in (EXPLOITABLE, CONDITIONAL)  # noqa: E731
        answers, yes, no, errors = vote(lambda: self.judge.judge(f, base["evidence"]), positive, lambda r: r["tier"] is None, self.checks)
        votes["exploit"] = {"yes": yes, "cast": yes + no, "errors": errors}
        if not answers:                         # the exploitability check never ran: the claim stays confirmed but says so
            return {**base, "votes": votes, "exploit": {"tier": "unchecked", "code": "error"}}
        if yes > no:
            tiers = [r["tier"] for r in answers if positive(r)]
            tier = CONDITIONAL if CONDITIONAL in tiers else EXPLOITABLE      # votes that differ: the more cautious label wins
            best = next(r for r in answers if r["tier"] == tier)
            return {**base, "votes": votes, "exploit": {**best, "agreement": f"{yes}/{yes + no}"}}
        negatives = [r for r in answers if not positive(r)]
        (_, code) = _most_common([(r["tier"], r["code"]) for r in negatives])
        best = next(r for r in negatives if r["code"] == code)
        return {"status": OBSERVATION, "code": code, "reasoning": best["reasoning"] or EXPLOIT_LABELS.get(code, code),
                "evidence": base["evidence"], "votes": votes, "exploit": {**best, "agreement": f"{no}/{yes + no}"}}

    # ------------------------------------------------------------------ reporting helpers
    @staticmethod
    def _feedback(r: dict[str, Any]) -> str:
        if r["status"] == OBSERVATION:
            quotes = "; ".join(f"{e['file']}:{e['line']} `{e['quote'][:120]}`" for e in r["evidence"][:2])
            return f"ACCURATE BUT NOT EXPLOITABLE ({EXPLOIT_LABELS.get(r['code'], r['code'])}): {r.get('reasoning', '')} {quotes}".strip()
        return CodeVerifier._feedback(r)

    @staticmethod
    def _record(f: Finding, r: dict[str, Any]) -> dict[str, Any]:
        rec = CodeVerifier._record(f, r)
        if r["status"] == OBSERVATION:
            rec["why"] = EXPLOIT_LABELS.get(r["code"], r["code"])
        rec["votes"], rec["exploit"] = r.get("votes") or {}, r.get("exploit") or {}
        return rec


def _split(votes: dict[str, Any]) -> bool:
    """True when the repeated checks did not all agree: the claim is borderline."""
    cc, ex = votes.get("code_check") or {}, votes.get("exploit") or {}
    return (0 < cc.get("confirmed", 0) < cc.get("cast", 0)) or (0 < ex.get("yes", 0) < ex.get("cast", 0))


def make_verifier(index: CodeIndex, llm, *, checks: int = DEFAULT_CHECKS, exploit: bool = True, **kw):
    """The verifier the command line and the evaluation tool use. `checks=1, exploit=False` behaves like the plain code check."""
    return ProvenVerifier(index, llm, checks=checks, exploit=exploit, **kw)
