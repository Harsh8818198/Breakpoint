"""NoteShare fixture -- a tiny, deliberately flawed HTTP app matching
blueprint.json in this directory. Used to prove the claim-verification
harness actually distinguishes a held claim from a falsified one, before
any real target or LLM agent is involved.

Two planted flaws (claims 1 and 2 in claims_data.py should come back
FALSIFIED), one correctly-enforced check (claim 3 should come back HELD) --
a true positive, a true positive, and a true negative, so the harness
itself is provably not just returning "falsified" for everything.

Stdlib http.server only, same as breakpoint.llm's own "stdlib urllib only"
philosophy -- this is a throwaway test fixture, not the real server.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

_SHARE_RE = re.compile(r"^/share/([^/]+)$")
_TEAM_NOTES_RE = re.compile(r"^/teams/([^/]+)/notes$")
_PRIVATE_RE = re.compile(r"^/notes/([^/]+)/private$")


def _seed_state() -> dict:
    return {
        "teams": {
            "team-a": {"id": "team-a", "name": "Team A"},
            "team-b": {"id": "team-b", "name": "Team B"},
        },
        "users": {
            "alice": {"id": "alice", "teamId": "team-a"},
            "bob": {"id": "bob", "teamId": "team-b"},
        },
        "notes": {
            "note-a1": {"id": "note-a1", "ownerId": "alice", "teamId": "team-a", "content": "Team A roadmap"},
            "note-b1": {"id": "note-b1", "ownerId": "bob", "teamId": "team-b", "content": "Team B payroll notes"},
        },
        "shareTokens": {"tok-a1": {"noteId": "note-a1"}},
    }


class _Handler(BaseHTTPRequestHandler):
    state: dict = {}  # overridden per-instance by a subclass from start_fixture()

    def log_message(self, fmt, *args):  # noqa: A002 -- stdlib signature
        pass  # keep test output quiet

    def _send(self, status: int, body) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 -- stdlib handler name
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        state = self.state

        # Share link: no owner check, no expiry -- planted flaw.
        m = _SHARE_RE.match(parsed.path)
        if m:
            entry = state["shareTokens"].get(m.group(1))
            if not entry:
                return self._send(404, {"error": "not found"})
            return self._send(200, state["notes"][entry["noteId"]])

        # Team notes listing: does not verify caller belongs to the team -- planted flaw.
        m = _TEAM_NOTES_RE.match(parsed.path)
        if m:
            team_id = m.group(1)
            if team_id not in state["teams"]:
                return self._send(404, {"error": "no such team"})
            notes = [n for n in state["notes"].values() if n["teamId"] == team_id]
            return self._send(200, notes)

        # Private note view: correctly checks ownership -- this one should hold.
        m = _PRIVATE_RE.match(parsed.path)
        if m:
            note = state["notes"].get(m.group(1))
            as_user = (qs.get("asUser") or [None])[0]
            requester = state["users"].get(as_user) if as_user else None
            if not note:
                return self._send(404, {"error": "not found"})
            if not requester or requester["id"] != note["ownerId"]:
                return self._send(403, {"error": "forbidden"})
            return self._send(200, note)

        self._send(404, {"error": "no route"})


class FixtureHandle:
    def __init__(self, httpd: HTTPServer, thread: threading.Thread, base_url: str):
        self._httpd = httpd
        self._thread = thread
        self.base_url = base_url

    def close(self) -> None:
        self._httpd.shutdown()
        self._thread.join()
        self._httpd.server_close()


def start_fixture() -> FixtureHandle:
    state = _seed_state()
    handler_cls = type("_SeededHandler", (_Handler,), {"state": state})
    httpd = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return FixtureHandle(httpd, thread, f"http://127.0.0.1:{port}")
