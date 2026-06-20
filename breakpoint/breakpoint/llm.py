"""Provider-agnostic LLM client.

Set BREAKPOINT_PROVIDER to one of: anthropic | openai | gemini
- anthropic : reads ANTHROPIC_API_KEY  (default model: claude-sonnet-4-6)
- openai    : reads OPENAI_API_KEY     (default model: gpt-4o)
- gemini    : reads GEMINI_API_KEY     (default model: gemini-2.0-flash)

Keys are loaded automatically from a .env file in the project root.
No external dependencies required (stdlib urllib only).
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import re
import time
import urllib.request
import urllib.error


def _load_dotenv() -> None:
    """Load .env into os.environ (stdlib only — no python-dotenv required).
    Searches the package directory and its parent (project root)."""
    for candidate in (pathlib.Path(__file__).parent, pathlib.Path(__file__).parent.parent):
        env_file = candidate / ".env"
        if not env_file.exists():
            continue
        with open(env_file, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.split("#", 1)[0].strip()  # drop inline comments
                os.environ.setdefault(key, val)
        break


_load_dotenv()


class LLMClient:
    def __init__(self, provider: str | None = None, model: str | None = None):
        self.provider = (provider or os.getenv("BREAKPOINT_PROVIDER", "anthropic")).lower()
        self.model = model or os.getenv("BREAKPOINT_MODEL", self._default_model())

    def _default_model(self) -> str:
        return {
            "anthropic": "claude-sonnet-4-6",
            "openai":    "gpt-4o",
            "gemini":    "gemini-2.0-flash-lite",
        }.get(self.provider, "claude-sonnet-4-6")

    @property
    def max_workers(self) -> int:
        """Concurrency ceiling that keeps us inside each provider's rate limits."""
        return {"anthropic": 8, "openai": 3, "gemini": 1}.get(self.provider, 4)

    def scale_tokens(self, base: int) -> int:
        """Add headroom for thinking models that burn tokens on internal reasoning."""
        if self.provider == "gemini" and "gemma" in self.model.lower():
            return base + 2000
        return base

    def complete(self, system: str, user: str, *, task: str = "", max_tokens: int = 2000) -> str:
        """Return the model's raw text response."""
        if self.provider == "anthropic":
            return self._anthropic(system, user, max_tokens)
        if self.provider == "openai":
            return self._openai(system, user, max_tokens)
        if self.provider == "gemini":
            return self._gemini(system, user, max_tokens)
        raise ValueError(
            f"Unknown provider: {self.provider!r}. "
            "Set BREAKPOINT_PROVIDER to anthropic, openai, or gemini in your .env file."
        )

    # --- providers -------------------------------------------------------

    def _anthropic(self, system: str, user: str, max_tokens: int) -> str:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key or key == "your-key-here":
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set.\n"
                "  Edit .env and set:  ANTHROPIC_API_KEY=sk-ant-...\n"
                "  Get a key at:       https://console.anthropic.com/settings/keys"
            )
        body = json.dumps({
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "content-type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
        )
        data = self._send(req)
        return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")

    def _openai(self, system: str, user: str, max_tokens: int) -> str:
        key = os.getenv("OPENAI_API_KEY", "")
        if not key or key == "your-key-here":
            raise RuntimeError(
                "OPENAI_API_KEY is not set.\n"
                "  Edit .env and set:  OPENAI_API_KEY=sk-...\n"
                "  Get a key at:       https://platform.openai.com/api-keys"
            )
        body = json.dumps({
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {key}"},
        )
        data = self._send(req)
        return data["choices"][0]["message"]["content"]

    def _gemini(self, system: str, user: str, max_tokens: int) -> str:
        key = os.getenv("GEMINI_API_KEY", "")
        if not key or key == "your-key-here":
            raise RuntimeError(
                "GEMINI_API_KEY is not set.\n"
                "  Edit .env and set:  GEMINI_API_KEY=AIza...\n"
                "  Get a key at:       https://aistudio.google.com/apikey"
            )
        body = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }).encode()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={key}"
        )
        req = urllib.request.Request(
            url, data=body, headers={"content-type": "application/json"})
        data = self._send(req)
        parts = data["candidates"][0]["content"]["parts"]
        # Gemma 4 prepends thinking tokens (thought=true); skip them for the answer.
        answer_parts = [p["text"] for p in parts if not p.get("thought")]
        return "\n".join(answer_parts) if answer_parts else parts[-1]["text"]

    @staticmethod
    def _send(req: urllib.request.Request) -> dict:
        last_err: Exception | None = None
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                body = e.read().decode()
                if e.code == 429 and attempt < 5:
                    # Respect Retry-After or parse retry text in the body
                    wait = 0.0
                    try:
                        wait = float(e.headers.get("Retry-After", 0))
                    except (ValueError, TypeError):
                        pass
                    
                    if not wait:
                        # Parse Gemini's error body, e.g. "Please retry in 9.532764154s."
                        match = re.search(r"Please retry in\s+([0-9.]+)\s*s", body)
                        if match:
                            try:
                                wait = float(match.group(1)) + 0.5  # Add a tiny buffer
                            except ValueError:
                                pass
                    
                    if not wait:
                        wait = 5.0 * (2 ** attempt)  # Safer fallback for free tier
                    
                    wait += random.uniform(0.1, 1.0)
                    last_err = RuntimeError(f"Rate limited (429) — retrying in {wait:.1f}s")
                    time.sleep(wait)
                    continue
                if e.code in (500, 502, 503, 504) and attempt < 5:
                    wait = (2 ** attempt) + random.uniform(0.1, 0.5)
                    last_err = RuntimeError(f"LLM HTTP {e.code}: {body[:200]}")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"LLM HTTP {e.code}: {body[:500]}") from e
            except urllib.error.URLError as e:
                if attempt < 5:
                    last_err = RuntimeError(f"LLM connection error: {e}")
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"LLM connection error: {e}") from e
        raise last_err  # type: ignore


# ---------------------------------------------------------------------------
# JSON extraction — must survive real LLM output quirks
# ---------------------------------------------------------------------------

_TRAIL_COMMA = re.compile(r",\s*([}\]])")
_PY_BOOL_NONE = (
    (re.compile(r"\bTrue\b"),  "true"),
    (re.compile(r"\bFalse\b"), "false"),
    (re.compile(r"\bNone\b"),  "null"),
)


def _sanitize(s: str) -> str:
    """Repair the most common LLM JSON formatting mistakes before parsing."""
    s = _TRAIL_COMMA.sub(r"\1", s)
    for pattern, replacement in _PY_BOOL_NONE:
        s = pattern.sub(replacement, s)
    return s


def extract_json(text: str):
    """Pull a JSON object/array out of an LLM response.

    Handles: markdown code fences, surrounding prose, trailing commas,
    Python-style True/False/None, and minor whitespace issues.
    """
    t = text.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if t.startswith("```"):
        inner = t.split("```", 2)
        if len(inner) >= 2:
            t = inner[1]
            if t.startswith("json"):
                t = t[4:]
            t = t.strip()

    # Find the outermost JSON container and sanitize before parsing
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = t.find(open_c), t.rfind(close_c)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(_sanitize(t[i:j + 1]))
            except json.JSONDecodeError:
                continue

    return json.loads(_sanitize(t))   # last resort — raises with a clear message
