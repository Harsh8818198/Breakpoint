"""The intended behaviour of NoteShare, expressed as claims checked over a request log.

Deliberately re-implemented from the written policy rather than imported from
the app: an oracle that shared the app's logic would pass the app's own flaws.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from .noteshare import FREE_QUOTA, SEED_NOTES, SEED_USERS

CLAIMS = {
    "READ_AUTHZ": "A note can be read only by its owner, someone it was shared with, or an admin.",
    "WRITE_AUTHZ": "Only a note's owner can update, delete, share, unshare or link it.",
    "SHARE_TENANCY": "A note can only be shared with users in the owner's org.",
    "QUOTA": f"A free-plan user owns at most {FREE_QUOTA} live notes.",
    "REVOKE": "After unshare_all, neither a former recipient nor the old public link can read the note.",
}

# The claim each planted flaw breaks. WRITE_AUTHZ guards a decoy and has no flaw.
FLAW_OF_CLAIM = {"READ_AUTHZ": "IDOR_READ", "SHARE_TENANCY": "CROSS_TENANT_SHARE",
                 "QUOTA": "IMPORT_NO_QUOTA", "REVOKE": "STALE_LINK"}


@dataclass(frozen=True)
class Violation:
    claim: str
    step: int      # index into the request log
    detail: str


@dataclass
class _Note:
    owner: str
    shared: set = field(default_factory=set)
    revoked: set = field(default_factory=set)
    link_active: bool = False
    deleted: bool = False


def check(log: list[dict]) -> list[Violation]:
    users = copy.deepcopy(SEED_USERS)
    notes = {i: _Note(owner=o) for i, o, _ in SEED_NOTES}
    tokens: dict[str, int] = {}
    out: list[Violation] = []

    def bad(claim: str, step: int, detail: str) -> None:
        out.append(Violation(claim, step, detail))

    def is_admin(actor) -> bool:
        return users.get(actor, {}).get("role") == "admin"

    for i, ev in enumerate(log):
        if not 200 <= ev["status"] < 300:
            continue  # the app refused the request, so there is nothing to violate
        actor, method, path, resp = ev["actor"], ev["method"], ev["path"], ev["resp"]

        if method == "GET" and (m := re.fullmatch(r"/s/([\w-]+)", path)):
            n = notes.get(tokens.get(m[1]))
            if n is None:
                bad("READ_AUTHZ", i, "a link that was never issued served a note")
            elif n.deleted or not n.link_active:
                bad("REVOKE", i, f"link {m[1]} still served its note after access was revoked")
            continue

        if method == "POST" and path in ("/notes", "/notes/import"):
            for nid in resp.get("ids", []):
                notes[nid] = _Note(owner=actor)
            live = sum(1 for n in notes.values() if n.owner == actor and not n.deleted)
            if users[actor]["plan"] == "free" and live > FREE_QUOTA:
                bad("QUOTA", i, f"{actor} (free plan) now owns {live} notes")
            continue

        if method == "GET" and (m := re.fullmatch(r"/admin/notes/(\d+)", path)):
            if not is_admin(actor):
                bad("READ_AUTHZ", i, f"{actor} read note {m[1]} through the admin route")
            continue

        m = re.fullmatch(r"/notes/(\d+)(?:/(share|unshare_all|link))?", path)
        if not m:
            continue
        nid, action = int(m[1]), m[2]
        n = notes.get(nid)
        if n is None:
            bad("READ_AUTHZ" if method == "GET" else "WRITE_AUTHZ", i, f"unknown note {nid} served")
            continue

        if action is None and method == "GET":
            if n.deleted or not (actor == n.owner or actor in n.shared or is_admin(actor)):
                bad("REVOKE" if actor in n.revoked else "READ_AUTHZ", i,
                    f"{actor} read note {nid} without access")
        elif actor != n.owner:
            bad("WRITE_AUTHZ", i, f"{actor} did {method} {path} on a note they do not own")
        elif action is None and method == "DELETE":
            n.deleted = True
        elif action == "share":
            target = ev["body"].get("user")
            if users.get(target, {}).get("org") != users[actor]["org"]:
                bad("SHARE_TENANCY", i, f"{actor} (org {users[actor]['org']}) shared note {nid} with {target}")
            else:
                n.shared.add(target)
        elif action == "unshare_all":
            n.revoked |= n.shared
            n.shared.clear()
            n.link_active = False
        elif action == "link":
            tokens[resp["token"]] = nid
            n.link_active = True
    return out
