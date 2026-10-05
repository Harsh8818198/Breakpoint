import { sendRequest, runAttackLoop } from "@/lib/services/attackAgent";

/**
 * Fires one request fresh and runs the claim's own predicate on the
 * response. This is the only place a verdict gets computed — neither the
 * attack loop nor the agent's own reasoning decides it (see RECEIPT,
 * arXiv 2607.18575, on agents satisfying a verifier without a reproducible
 * exploit).
 */
export async function replayAndCheck(claim, request, baseUrl) {
  const { status, body } = await sendRequest(baseUrl, request);
  const { held, note } = claim.checkResponse(status, body);
  return { status: held ? "held" : "falsified", note, request };
}

/**
 * Fast, free, no-LLM regression check: replays each claim's known
 * (hand-coded) exploit attempt and confirms the predicate still reads it
 * correctly. Useful as a sanity check on the harness itself, independent
 * of whether an agent can find the exploit on its own.
 */
export async function runGoldenRegression(claims, baseUrl) {
  const results = [];
  for (const claim of claims) {
    const { status, note } = await replayAndCheck(claim, claim.goldenAttempt, baseUrl);
    results.push({ id: claim.id, statement: claim.statement, severity: claim.severity, status, note });
  }
  return summarize(results);
}

/**
 * Agent-driven verification: for each claim, an LLM explores a fresh
 * instance of the target over HTTP only, with no hint about which endpoint
 * is flawed. If it concludes the claim is falsified, its exact proof
 * request is replayed against a second, independent fresh instance before
 * the verdict counts — the agent's own transcript is never trusted as proof.
 */
export async function runAgentClaimVerification(llm, claims, apiSurface, startFixtureFn, { maxTurns = 6 } = {}) {
  const results = [];

  for (const claim of claims) {
    const exploration = await startFixtureFn();
    let attack;
    try {
      attack = await runAttackLoop(llm, claim, apiSurface, exploration.baseUrl, { maxTurns });
    } finally {
      await exploration.close();
    }

    const base = { id: claim.id, statement: claim.statement, severity: claim.severity, turns: attack.turns };

    if (!attack.concluded) {
      results.push({ ...base, status: "inconclusive", note: attack.reasoning });
      continue;
    }

    if (!attack.claimedFalsified) {
      results.push({ ...base, status: "held", note: `agent found no violation: ${attack.reasoning}` });
      continue;
    }

    if (!attack.proofRequest) {
      results.push({ ...base, status: "agent_claim_unverified", note: "agent claimed falsified but gave no proof request" });
      continue;
    }

    const replayTarget = await startFixtureFn();
    let verdict;
    try {
      verdict = await replayAndCheck(claim, attack.proofRequest, replayTarget.baseUrl);
    } finally {
      await replayTarget.close();
    }

    const confirmed = verdict.status === "falsified";
    results.push({
      ...base,
      status: confirmed ? "falsified" : "agent_claim_unverified",
      note: confirmed
        ? `confirmed by independent replay: ${verdict.note}`
        : `agent claimed falsified, replay did not reproduce it: ${verdict.note}`,
      proofRequest: attack.proofRequest,
      agentReasoning: attack.reasoning,
    });
  }

  return summarize(results);
}

function summarize(results) {
  const count = (status) => results.filter((r) => r.status === status).length;
  return {
    results,
    heldCount: count("held"),
    falsifiedCount: count("falsified"),
    inconclusiveCount: count("inconclusive"),
    unverifiedCount: count("agent_claim_unverified"),
  };
}
