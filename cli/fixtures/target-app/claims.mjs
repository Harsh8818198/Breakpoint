/**
 * Claims for the NoteShare fixture, with hand-written verifiers.
 *
 * Each verify(baseUrl) talks to the fixture only over HTTP — the same
 * interface an attacker would have. No reaching into server state directly.
 * That's deliberate: a verifier that can inspect internals instead of
 * observed behavior isn't trustworthy evidence (see RECEIPT, arXiv 2607.18575,
 * on agents satisfying a verifier without a reproducible exploit).
 */

export const claims = [
  {
    id: "share-link-scoped",
    statement: "A share link only exposes the note it was created for, and cannot be used to reach unrelated notes.",
    severity: "high",
    async verify(baseUrl) {
      const res = await fetch(`${baseUrl}/share/tok-a1`);
      const body = await res.json();
      // The flaw: the share endpoint returns full note content with no
      // expiry or recipient check at all — any holder of the token, forever,
      // gets full access. We treat "succeeds with no gating" as the violation.
      const held = res.status !== 200 || !body.content;
      return {
        held,
        evidence: `GET /share/tok-a1 -> ${res.status} ${JSON.stringify(body)}`,
      };
    },
  },
  {
    id: "tenant-isolation",
    statement: "A user cannot list another team's notes.",
    severity: "critical",
    async verify(baseUrl) {
      // Bob (team-b) asks to list team-a's notes.
      const res = await fetch(`${baseUrl}/teams/team-a/notes?asUser=bob`);
      const body = await res.json();
      const held = res.status === 403 || (Array.isArray(body) && body.length === 0);
      return {
        held,
        evidence: `GET /teams/team-a/notes?asUser=bob -> ${res.status} ${JSON.stringify(body)}`,
      };
    },
  },
  {
    id: "private-note-ownership",
    statement: "A user cannot view another user's private note directly.",
    severity: "critical",
    async verify(baseUrl) {
      // Bob (team-b) asks for Alice's (team-a) private note. This endpoint
      // checks ownership correctly, so this claim should hold.
      const res = await fetch(`${baseUrl}/notes/note-a1/private?asUser=bob`);
      const body = await res.json();
      const held = res.status === 403;
      return {
        held,
        evidence: `GET /notes/note-a1/private?asUser=bob -> ${res.status} ${JSON.stringify(body)}`,
      };
    },
  },
];
