"""Count what a run spends: model calls, characters sent and received, seconds.

`MeteredLLM` wraps any client that has `complete()` and records every call, so a run can report calls and an estimated
token count next to its results. The token figure is an ESTIMATE (characters / 4); providers report exact usage and a
later step will use that. Calls that raise are counted as failed calls and the exception passes through unchanged.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class UsageMeter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "failed": 0, "prompt_chars": 0,
                                                                        "completion_chars": 0, "seconds": 0.0})

    def record(self, task: str, prompt_chars: int, completion_chars: int, seconds: float, failed: bool = False) -> None:
        with self._lock:
            r = self._rows[task or "unlabelled"]
            r["calls"] += 1
            r["failed"] += int(failed)
            r["prompt_chars"] += prompt_chars
            r["completion_chars"] += completion_chars
            r["seconds"] += seconds

    def snapshot(self) -> dict:
        """{"calls", "failed", "est_tokens", "seconds_in_calls", "by_task": {task: {...}}}"""
        with self._lock:
            by_task = {t: dict(r, est_tokens=round((r["prompt_chars"] + r["completion_chars"]) / 4))
                       for t, r in sorted(self._rows.items())}
        total = {"calls": 0, "failed": 0, "prompt_chars": 0, "completion_chars": 0, "seconds": 0.0}
        for r in by_task.values():
            for k in total:
                total[k] += r[k]
        return {"calls": int(total["calls"]), "failed": int(total["failed"]),
                "est_tokens": round((total["prompt_chars"] + total["completion_chars"]) / 4),
                "seconds_in_calls": round(total["seconds"], 1), "by_task": by_task}


class MeteredLLM:
    """Looks like the wrapped client (provider, model, max_workers, scale_tokens, complete) and counts every call."""

    def __init__(self, inner, meter: UsageMeter | None = None) -> None:
        self._inner = inner
        self.meter = meter or UsageMeter()

    def __getattr__(self, name):                  # provider, model, max_workers, scale_tokens, ...
        return getattr(self._inner, name)

    def complete(self, system: str, user: str, *, task: str = "", max_tokens: int = 2000) -> str:
        started, sent = time.monotonic(), len(system) + len(user)
        try:
            out = self._inner.complete(system, user, task=task, max_tokens=max_tokens)
        except BaseException:
            self.meter.record(task, sent, 0, time.monotonic() - started, failed=True)
            raise
        self.meter.record(task, sent, len(out or ""), time.monotonic() - started)
        return out
