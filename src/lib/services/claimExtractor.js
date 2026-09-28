import connectDB from "@/lib/db/connect";
import Claim from "@/lib/db/models/Claim";
import { getClaimExtractionPrompt } from "@/lib/prompts/blueprint/claimExtraction";

const VALID_CATEGORIES = new Set([
  "auth",
  "rate_limit",
  "data_isolation",
  "payment",
  "business_logic",
  "ux",
  "compliance",
  "other",
]);

const VALID_SEVERITIES = new Set(["critical", "high", "medium", "low"]);

/**
 * Extract claims from a blueprint via the LLM. Pure function — no DB access,
 * so it can run from the CLI against a blueprint JSON file with no simulation
 * context yet.
 *
 * @param {BaseLLMProvider} llm
 * @param {Object} blueprint - plain object (Blueprint.toJSON() shape)
 * @returns {Promise<Array<Object>>} normalized claims, not yet persisted
 */
export async function extractClaims(llm, blueprint) {
  const prompt = getClaimExtractionPrompt(blueprint);
  const result = await llm.chatJSON([{ role: "user", content: prompt }]);
  const rawClaims = Array.isArray(result.data?.claims) ? result.data.claims : [];
  return rawClaims.map(normalizeClaim).filter(Boolean);
}

/**
 * Persist extracted claims for a simulation. Separate from extraction so the
 * CLI can inspect claims before anything touches the database.
 *
 * @param {string} simulationId
 * @param {string} blueprintId
 * @param {Array<Object>} claims - normalized claims from extractClaims()
 */
export async function persistClaims(simulationId, blueprintId, claims) {
  await connectDB();
  const docs = claims.map((claim) => ({ ...claim, simulationId, blueprintId }));
  const saved = await Claim.insertMany(docs);
  return saved.map((c) => c.toJSON());
}

function normalizeClaim(raw) {
  if (!raw || typeof raw.statement !== "string" || !raw.statement.trim()) return null;

  const formalizable = Boolean(raw.formalizable);

  return {
    statement: raw.statement.trim(),
    category: VALID_CATEGORIES.has(raw.category) ? raw.category : "other",
    featureRefs: Array.isArray(raw.featureRefs) ? raw.featureRefs.map(String) : [],
    formalizable,
    predicate: formalizable && raw.predicate ? String(raw.predicate) : null,
    severityIfFalse: VALID_SEVERITIES.has(raw.severityIfFalse) ? raw.severityIfFalse : "medium",
    alpha: 1,
    beta: 1,
    testCount: 0,
    status: "active",
  };
}
