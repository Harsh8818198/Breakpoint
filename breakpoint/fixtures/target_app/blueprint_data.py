"""A Blueprint describing exactly what server.py implements -- no richer,
no thinner. Used to sanity-check claims.extract_claims() against the three
hand-written claims in claims_data.py: a fair comparison needs a blueprint
that doesn't describe features the fixture doesn't actually have.

Built directly as a Blueprint object rather than round-tripped through the
LLM (blueprint.py has no JSON-loading path yet) -- this fixture needs to be
deterministic.
"""

from __future__ import annotations

from breakpoint.models import Blueprint, Flow

FIXTURE_BLUEPRINT = Blueprint(
    name="NoteShare (fixture)",
    type="HTTP JSON API",
    domain="Productivity",
    stage="beta",
    actors=[
        "alice -- team member of team-a, owns note-a1, issued share token tok-a1 for it",
        "bob -- team member of team-b, owns note-b1",
    ],
    resources=[
        "note-a1 -- owned by alice, belongs to team-a, sensitivity: private",
        "note-b1 -- owned by bob, belongs to team-b, sensitivity: private",
        "tok-a1 -- a share token alice issued for note-a1, sensitivity: sensitive",
    ],
    boundaries=[
        "No share token -> Has share token: alice shares a note and hands out the token; "
        "holding a share token is meant to grant access only to the specific note it was issued for",
        "Outside a team -> Inside a team: membership in team-a or team-b is meant to scope "
        "which notes a user can list or read",
    ],
    flows=[
        Flow(
            name="View a note via share link",
            steps=[
                "GET /share/:token -- returns the note the token was issued for",
                "(ASSUMED gap) token never expires, no check the requester is the intended recipient",
            ],
        ),
        Flow(
            name="List a team's notes",
            steps=[
                "GET /teams/:teamId/notes?asUser=<userId> -- returns all notes belonging to teamId",
                "(ASSUMED gap) asUser is not verified against teamId before returning data",
            ],
        ),
        Flow(
            name="View a private note",
            steps=[
                "GET /notes/:id/private?asUser=<userId> -- returns the note only if asUser is its owner",
            ],
        ),
    ],
    mechanical_details=[
        "Share links: no expiry, no recipient check (?)",
        "Team notes listing: asUser not checked against teamId (?)",
        "Private note view: ownership correctly enforced",
    ],
    known_unknowns=[
        "Whether share links were ever intended to expire",
        "Whether team membership should gate the team notes listing endpoint",
    ],
    attack_surface=[
        "Share links -- no expiry, no recipient check",
        "Team notes listing -- asUser not checked against teamId",
    ],
)
