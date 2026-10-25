import io
import json
import unittest
import urllib.error
from unittest import mock

from breakpoint.llm import LLMClient, LLMFatalError, fatal_reason


def http_error(code, body):
    return urllib.error.HTTPError("https://api.example/x", code, "err", {}, io.BytesIO(body.encode()))


OPENAI_NO_CREDIT = json.dumps({"error": {"message": "You have no credits remaining.", "type": "insufficient_quota",
                                         "code": "credit_balance_exhausted"}})
ANTHROPIC_NO_CREDIT = json.dumps({"error": {"type": "invalid_request_error",
                                            "message": "Your credit balance is too low to access the Anthropic API."}})
GEMINI_PER_MINUTE = ("Quota exceeded for metric generate_content_free_tier_requests, limit: 15. "
                     "Please retry in 9.5s.")


class WhatCannotBeRetried(unittest.TestCase):
    def test_no_credit_bad_key_and_unknown_model_are_fatal(self):
        self.assertIn("no credit", fatal_reason(429, OPENAI_NO_CREDIT))
        self.assertIn("no credit", fatal_reason(400, ANTHROPIC_NO_CREDIT))
        self.assertIn("rejected the API key", fatal_reason(401, "Incorrect API key"))
        self.assertIn("BREAKPOINT_MODEL", fatal_reason(404, "The model `gpt-9` does not exist"))

    def test_a_per_minute_limit_and_ordinary_errors_are_not_fatal(self):
        self.assertIsNone(fatal_reason(429, GEMINI_PER_MINUTE))
        self.assertIsNone(fatal_reason(429, "Rate limit reached for requests"))
        self.assertIsNone(fatal_reason(503, "overloaded"))
        self.assertIsNone(fatal_reason(400, "bad request: temperature must be <= 2"))


class SendBehaviour(unittest.TestCase):
    def test_out_of_credit_stops_at_once_without_retrying_or_sleeping(self):
        calls = []

        def boom(*a, **k):
            calls.append(1)
            raise http_error(429, OPENAI_NO_CREDIT)

        with mock.patch("urllib.request.urlopen", boom), mock.patch("time.sleep") as sleep:
            with self.assertRaises(LLMFatalError):
                LLMClient._send(mock.Mock())
        self.assertEqual(len(calls), 1)
        sleep.assert_not_called()

    def test_a_normal_rate_limit_still_retries(self):
        class Ok:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"ok": true}'

        seq = [http_error(429, "Rate limit reached"), Ok()]

        def fake(*a, **k):
            r = seq.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch("urllib.request.urlopen", fake), mock.patch("time.sleep") as sleep:
            self.assertEqual(LLMClient._send(mock.Mock()), {"ok": True})
        sleep.assert_called_once()


class ATransient403(unittest.TestCase):
    class Ok:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": true}'

    def send(self, seq):
        calls = []

        def fake(*a, **k):
            calls.append(1)
            r = seq.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch("urllib.request.urlopen", fake), mock.patch("time.sleep") as sleep:
            try:
                return LLMClient._send(mock.Mock()), len(calls), sleep.call_count
            except LLMFatalError:
                return "fatal", len(calls), sleep.call_count

    def test_a_403_that_clears_is_retried(self):
        out, calls, sleeps = self.send([http_error(403, "denied"), http_error(403, "denied"), self.Ok()])
        self.assertEqual((out, calls, sleeps), ({"ok": True}, 3, 2))

    def test_a_403_that_persists_is_fatal_after_a_few_short_waits(self):
        out, calls, sleeps = self.send([http_error(403, "denied")] * 5)
        self.assertEqual((out, calls, sleeps), ("fatal", 4, 3))

    def test_a_401_is_still_fatal_at_once(self):
        out, calls, sleeps = self.send([http_error(401, "bad key")] * 5)
        self.assertEqual((out, calls, sleeps), ("fatal", 1, 0))

    def test_a_connection_that_drops_while_the_reply_is_being_read_is_retried(self):
        import http.client
        import ssl
        out, calls, sleeps = self.send([ssl.SSLError("read error"), ConnectionResetError("reset"),
                                        http.client.IncompleteRead(b"par"), self.Ok()])
        self.assertEqual((out, calls, sleeps), ({"ok": True}, 4, 3))


class VerifierDoesNotHideIt(unittest.TestCase):
    def test_fatal_errors_propagate_out_of_the_verifier(self):
        from breakpoint.codeindex import CodeIndex
        from breakpoint.codeverify import CodeVerifier
        from breakpoint.models import Finding
        from .test_codeindex import make_repo

        class Dead:
            max_workers = 1
            def scale_tokens(self, n): return n
            def complete(self, *a, **k): raise LLMFatalError("no credit")

        idx = CodeIndex.from_dir(make_repo({"a.py": "def get_user(name):\n    return name\n"}))
        f = Finding(title="Injection in get_user", generation=1, discovered_by="x", description="uses get_user")
        with self.assertRaises(LLMFatalError):
            CodeVerifier(idx, Dead())([f])


if __name__ == "__main__":
    unittest.main()
