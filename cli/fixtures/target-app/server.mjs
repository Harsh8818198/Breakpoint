import http from "node:http";

/**
 * NoteShare fixture — a tiny, deliberately flawed HTTP app matching
 * cli/fixtures/sample-blueprint.json. Used to prove the claim-verification
 * harness actually distinguishes a held claim from a falsified one, before
 * any real target or LLM agent is involved.
 *
 * Two planted flaws (claims 1 and 2 in claims.mjs should come back FALSIFIED),
 * one correctly-enforced check (claim 3 should come back HELD) — a true
 * positive, a true positive, and a true negative, so the harness itself is
 * provably not just returning "falsified" for everything.
 */

function seedState() {
  return {
    teams: {
      "team-a": { id: "team-a", name: "Team A" },
      "team-b": { id: "team-b", name: "Team B" },
    },
    users: {
      alice: { id: "alice", teamId: "team-a" },
      bob: { id: "bob", teamId: "team-b" },
    },
    notes: {
      "note-a1": { id: "note-a1", ownerId: "alice", teamId: "team-a", content: "Team A roadmap" },
      "note-b1": { id: "note-b1", ownerId: "bob", teamId: "team-b", content: "Team B payroll notes" },
    },
    shareTokens: {
      "tok-a1": { noteId: "note-a1" },
    },
  };
}

export function createFixtureServer() {
  const state = seedState();

  const server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://localhost");
    const send = (status, body) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(body));
    };

    // Share link: no owner check, no expiry — planted flaw.
    // GET /share/:token
    let m = url.pathname.match(/^\/share\/([^/]+)$/);
    if (m) {
      const entry = state.shareTokens[m[1]];
      if (!entry) return send(404, { error: "not found" });
      return send(200, state.notes[entry.noteId]);
    }

    // Team notes listing: does not verify the caller belongs to the team — planted flaw.
    // GET /teams/:teamId/notes?asUser=<userId>
    m = url.pathname.match(/^\/teams\/([^/]+)\/notes$/);
    if (m) {
      const teamId = m[1];
      if (!state.teams[teamId]) return send(404, { error: "no such team" });
      const notes = Object.values(state.notes).filter((n) => n.teamId === teamId);
      return send(200, notes);
    }

    // Private note view: correctly checks ownership — this one should hold.
    // GET /notes/:id/private?asUser=<userId>
    m = url.pathname.match(/^\/notes\/([^/]+)\/private$/);
    if (m) {
      const note = state.notes[m[1]];
      const asUser = url.searchParams.get("asUser");
      const requester = state.users[asUser];
      if (!note) return send(404, { error: "not found" });
      if (!requester || requester.id !== note.ownerId) {
        return send(403, { error: "forbidden" });
      }
      return send(200, note);
    }

    send(404, { error: "no route" });
  });

  return server;
}

export function startFixture() {
  return new Promise((resolve) => {
    const server = createFixtureServer();
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      const baseUrl = `http://127.0.0.1:${port}`;
      resolve({
        baseUrl,
        close: () => new Promise((r) => server.close(r)),
      });
    });
  });
}
