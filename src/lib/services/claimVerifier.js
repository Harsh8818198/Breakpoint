/**
 * Runs a set of claim verifiers against a live target and reports which
 * claims held and which were falsified.
 *
 * This is the trusted verdict computer: it does not generate claims and it
 * does not attack anything itself — it only executes the verify() function
 * each claim already carries and records the result. Keeping this separate
 * from claim generation and from whatever produces attack attempts is what
 * keeps a verdict trustworthy once an agent is in the loop (see RECEIPT,
 * arXiv 2607.18575, on verifiers an agent can satisfy without a real exploit).
 *
 * @param {Array<{id: string, statement: string, severity: string, verify: (baseUrl: string) => Promise<{held: boolean, evidence: string}>}>} claims
 * @param {string} baseUrl - target to verify against
 * @returns {Promise<{results: Array<Object>, heldCount: number, falsifiedCount: number, erroredCount: number}>}
 */
export async function runClaimVerification(claims, baseUrl) {
  const results = [];

  for (const claim of claims) {
    const startedAt = Date.now();
    try {
      const { held, evidence } = await claim.verify(baseUrl);
      results.push({
        id: claim.id,
        statement: claim.statement,
        severity: claim.severity,
        status: held ? "held" : "falsified",
        evidence,
        durationMs: Date.now() - startedAt,
      });
    } catch (error) {
      results.push({
        id: claim.id,
        statement: claim.statement,
        severity: claim.severity,
        status: "error",
        evidence: error.message,
        durationMs: Date.now() - startedAt,
      });
    }
  }

  return {
    results,
    heldCount: results.filter((r) => r.status === "held").length,
    falsifiedCount: results.filter((r) => r.status === "falsified").length,
    erroredCount: results.filter((r) => r.status === "error").length,
  };
}
