/**
 * Claims for the NoteShare fixture.
 *
 * Each claim is split in two, on purpose:
 *  - checkResponse() is a pure, deterministic predicate over an HTTP
 *    response. It does not know or care which request produced that
 *    response — that's what keeps it reusable for both a hard-coded
 *    regression check and whatever request an attack agent chooses to try.
 *  - goldenAttempt is the known request that the original hand-written
 *    exploit used, kept only so `verify-fixture` can still run a fast,
 *    free, no-LLM regression check of the predicates themselves.
 *
 * apiSurface is what an attack agent is told about the target — real
 * endpoints and entities, same as a tester would get from the product's
 * blueprint, but with no hint about which endpoint is flawed. Finding that
 * out is the agent's job, not something handed to it.
 */

export const apiSurface = `
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
`.trim();

export const claims = [
  {
    id: "share-link-scoped",
    statement: "A share link only exposes the note it was created for, and cannot be used to reach unrelated notes.",
    severity: "high",
    goldenAttempt: { method: "GET", path: "/share/tok-a1" },
    checkResponse(status, body) {
      // The flaw: the share endpoint returns full note content with no
      // expiry or recipient check at all. "Succeeds with no gating" is
      // the violation here, since tok-a1 was only ever meant to share
      // note-a1 with whoever alice sent the link to.
      const held = status !== 200 || !body?.content;
      return { held, note: `status=${status} body=${JSON.stringify(body)}` };
    },
  },
  {
    id: "tenant-isolation",
    statement: "A user cannot list another team's notes.",
    severity: "critical",
    goldenAttempt: { method: "GET", path: "/teams/team-a/notes", query: { asUser: "bob" } },
    checkResponse(status, body) {
      const held = status === 403 || (Array.isArray(body) && body.length === 0);
      return { held, note: `status=${status} body=${JSON.stringify(body)}` };
    },
  },
  {
    id: "private-note-ownership",
    statement: "A user cannot view another user's private note directly.",
    severity: "critical",
    goldenAttempt: { method: "GET", path: "/notes/note-a1/private", query: { asUser: "bob" } },
    checkResponse(status, _body) {
      // This endpoint checks ownership correctly, so a well-aimed attempt
      // against it should come back held, not falsified.
      const held = status === 403;
      return { held, note: `status=${status}` };
    },
  },
];
