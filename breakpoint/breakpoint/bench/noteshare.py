"""NoteShare: a small multi-tenant notes app with deliberately planted flaws.

Each flaw sits behind a flag, so the same code is also its own patched build:
a fix is verified by re-running the exploit with that flag removed.
"""

from __future__ import annotations

import copy
import re
import secrets
from dataclasses import dataclass

FREE_QUOTA = 5

FLAWS = {
    "IDOR_READ": "GET /notes/{id} checks login but not ownership or sharing",
    "CROSS_TENANT_SHARE": "sharing never checks the recipient is in the owner's org",
    "IMPORT_NO_QUOTA": "bulk import skips the free-plan note quota",
    "STALE_LINK": "unshare_all clears the share list but the public link keeps working",
}
ALL_FLAWS = frozenset(FLAWS)

SEED_USERS = {
    "alice": {"org": "A", "role": "member", "plan": "free"},
    "bob": {"org": "A", "role": "member", "plan": "free"},
    "carol": {"org": "B", "role": "member", "plan": "pro"},
    "root": {"org": "A", "role": "admin", "plan": "pro"},
}
SEED_NOTES = [(1, "alice", "alice private plans"),
              (2, "bob", "bob draft"),
              (3, "carol", "carol roadmap")]


@dataclass
class Response:
    status: int
    body: dict


def _view(n: dict) -> dict:
    return {"id": n["id"], "owner": n["owner"], "title": n["title"], "body": n["body"]}


class NoteShare:
    def __init__(self, flaws=ALL_FLAWS):
        self.flaws = frozenset(flaws)
        self.users = copy.deepcopy(SEED_USERS)
        self.notes = {i: {"id": i, "owner": o, "title": t, "body": "",
                          "shared": set(), "link": None, "deleted": False}
                      for i, o, t in SEED_NOTES}
        self.log: list[dict] = []
        self._next_id = max(self.notes) + 1

    def request(self, actor: str | None, method: str, path: str, body: dict | None = None) -> Response:
        method, body = method.upper(), body or {}
        resp = self._route(actor, method, path, body)
        self.log.append({"actor": actor, "method": method, "path": path, "body": body,
                         "status": resp.status, "resp": resp.body})
        return resp

    def _route(self, actor, method, path, body) -> Response:
        if actor is not None and actor not in self.users:
            return Response(401, {"error": "unknown user"})
        if method == "GET" and (m := re.fullmatch(r"/s/([\w-]+)", path)):
            return self._read_link(m[1])
        if actor is None:
            return Response(401, {"error": "login required"})
        if method == "POST" and path == "/notes":
            return self._create(actor, [body], enforce_quota=True)
        if method == "POST" and path == "/notes/import":
            items = body.get("notes")
            if not isinstance(items, list) or not items:
                return Response(400, {"error": "notes must be a non-empty list"})
            return self._create(actor, items, enforce_quota="IMPORT_NO_QUOTA" not in self.flaws)
        if method == "GET" and (m := re.fullmatch(r"/admin/notes/(\d+)", path)):
            return self._admin_read(actor, int(m[1]))
        m = re.fullmatch(r"/notes/(\d+)(?:/(share|unshare_all|link))?", path)
        if not m:
            return Response(404, {"error": "no such route"})
        n = self.notes.get(int(m[1]))
        if n is None or n["deleted"]:
            return Response(404, {"error": "no such note"})
        action = m[2]
        if action is None:
            if method == "GET":
                return self._read(actor, n)
            if method == "PUT":
                return self._update(actor, n, body)
            if method == "DELETE":
                return self._delete(actor, n)
        elif method == "POST":
            if actor != n["owner"]:
                return Response(403, {"error": "owner only"})
            return {"share": self._share, "unshare_all": self._unshare_all,
                    "link": self._link}[action](n, body)
        return Response(405, {"error": "method not allowed"})

    def _create(self, actor, items, enforce_quota) -> Response:
        if not all(isinstance(i, dict) for i in items):
            return Response(400, {"error": "each note must be an object"})
        owned = sum(1 for n in self.notes.values() if n["owner"] == actor and not n["deleted"])
        if enforce_quota and self.users[actor]["plan"] == "free" and owned + len(items) > FREE_QUOTA:
            return Response(402, {"error": "free plan note limit reached"})
        ids = []
        for item in items:
            nid, self._next_id = self._next_id, self._next_id + 1
            self.notes[nid] = {"id": nid, "owner": actor, "title": str(item.get("title", "untitled"))[:80],
                               "body": str(item.get("body", "")), "shared": set(), "link": None,
                               "deleted": False}
            ids.append(nid)
        return Response(201, {"ids": ids, "id": ids[0]})

    def _may_read(self, actor, n) -> bool:
        return actor == n["owner"] or actor in n["shared"] or self.users[actor]["role"] == "admin"

    def _read(self, actor, n) -> Response:
        if "IDOR_READ" not in self.flaws and not self._may_read(actor, n):
            return Response(403, {"error": "forbidden"})
        return Response(200, _view(n))

    def _update(self, actor, n, body) -> Response:
        if actor != n["owner"]:
            return Response(403, {"error": "owner only"})
        n["body"] = str(body.get("body", n["body"]))
        return Response(200, _view(n))

    def _delete(self, actor, n) -> Response:
        if actor != n["owner"]:
            return Response(403, {"error": "owner only"})
        n["deleted"] = True
        return Response(200, {"deleted": n["id"]})

    def _share(self, n, body) -> Response:
        target = body.get("user")
        if target not in self.users:
            return Response(404, {"error": "no such user"})
        if "CROSS_TENANT_SHARE" not in self.flaws and self.users[target]["org"] != self.users[n["owner"]]["org"]:
            return Response(403, {"error": "can only share within your org"})
        n["shared"].add(target)
        return Response(200, {"shared_with": sorted(n["shared"])})

    def _unshare_all(self, n, body) -> Response:
        n["shared"].clear()
        if "STALE_LINK" not in self.flaws:
            n["link"] = None
        return Response(200, {"shared_with": []})

    def _link(self, n, body) -> Response:
        n["link"] = secrets.token_urlsafe(8)
        return Response(200, {"token": n["link"]})

    def _read_link(self, token) -> Response:
        for n in self.notes.values():
            if n["link"] == token and not n["deleted"]:
                return Response(200, _view(n))
        return Response(404, {"error": "no such link"})

    def _admin_read(self, actor, nid) -> Response:
        n = self.notes.get(nid)
        if self.users[actor]["role"] != "admin":
            return Response(403, {"error": "admin only"})
        if n is None or n["deleted"]:
            return Response(404, {"error": "no such note"})
        return Response(200, _view(n))
