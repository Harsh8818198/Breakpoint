"""Claims for the NoteShare fixture.

Each claim is split in two, on purpose:
  - check_response() is a pure, deterministic predicate over an HTTP
    response. It does not know or care which request produced that
    response -- that's what keeps it reusable for both a hard-coded
    regression check and whatever request an attack agent chooses to try.
  - golden_attempt is the known request the original hand-written exploit
    used, kept only so the free regression check can run without an LLM.

api_surface is what an attack agent is told about the target -- real
endpoints and entities, same as a tester would get from the product's
blueprint, but with no hint about which endpoint is flawed. Finding that
out is the agent's job, not something handed to it.
"""

from __future__ import annotations

from breakpoint.claim_verifier import FixtureClaim

api_surface = """
Target: NoteShare, a note-sharing app for small teams.

Known endpoints:
  GET /share/:token
    Fetch a note via a share token.
  GET /teams/:teamId/notes?asUser=<userId>
    List notes belonging to a team, on behalf of the given user.
  GET /notes/:id/private?asUser=<userId>
    Fetch a single note directly, on behalf of the given user.

Known entities:
  Users: alice (member of team-a), bob (member of team-b)
  Teams: team-a, team-b
  Notes: note-a1 (owned by alice, belongs to team-a), note-b1 (owned by bob, belongs to team-b)
  Share tokens: tok-a1 (was issued by alice for note-a1)
""".strip()


def _share_link_scoped(status: int, body) -> tuple[bool, str]:
    # The flaw: the share endpoint returns full note content with no
    # expiry or recipient check at all. "Succeeds with no gating" is the
    # violation, since tok-a1 was only ever meant to share note-a1 with
    # whoever alice sent the link to.
    held = status != 200 or not (isinstance(body, dict) and body.get("content"))
    return held, f"status={status} body={body}"


def _tenant_isolation(status: int, body) -> tuple[bool, str]:
    held = status == 403 or (isinstance(body, list) and len(body) == 0)
    return held, f"status={status} body={body}"


def _private_note_ownership(status: int, _body) -> tuple[bool, str]:
    # This endpoint checks ownership correctly, so a well-aimed attempt
    # against it should come back held, not falsified.
    return status == 403, f"status={status}"


claims = [
    FixtureClaim(
        id="share-link-scoped",
        statement="A share link only exposes the note it was created for, and cannot be used to reach unrelated notes.",
        severity="high",
        check_response=_share_link_scoped,
        golden_attempt={"path": "/share/tok-a1"},
    ),
    FixtureClaim(
        id="tenant-isolation",
        statement="A user cannot list another team's notes.",
        severity="critical",
        check_response=_tenant_isolation,
        golden_attempt={"path": "/teams/team-a/notes", "query": {"asUser": "bob"}},
    ),
    FixtureClaim(
        id="private-note-ownership",
        statement="A user cannot view another user's private note directly.",
        severity="critical",
        check_response=_private_note_ownership,
        golden_attempt={"path": "/notes/note-a1/private", "query": {"asUser": "bob"}},
    ),
]
