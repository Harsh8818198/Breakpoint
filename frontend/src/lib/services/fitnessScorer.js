import { cosineSimilarity } from "@/lib/utils/helpers";
import { EVOLUTION_CONFIG } from "@/lib/config/defaults";
import { getBSSSeverity } from "@/lib/config/constants";

/**
 * Score vulnerability fitness for natural selection.
 * Combines novelty (from embeddings) and severity (from BSS).
 */
export async function scoreFitness(vulnerability, existingFindings, llm) {
  let noveltyScore = 1.0; // Default: fully novel

  if (existingFindings.length > 0) {
    // Compute embedding for this vulnerability
    const vulnText = `${vulnerability.title}: ${vulnerability.description}`;
    const vulnEmbedding = await llm.embedText(vulnText);

    // Compare against all existing findings
    const existingTexts = existingFindings.map(
      (f) => `${f.title}: ${f.description}`
    );
    const existingEmbeddings = await Promise.all(
      existingTexts.map((t) => llm.embedText(t))
    );

    // Novelty = 1 - max_similarity (most novel = least similar to anything)
    const maxSimilarity = Math.max(
      ...existingEmbeddings.map((e) => cosineSimilarity(vulnEmbedding, e))
    );
    noveltyScore = 1 - maxSimilarity;
  }

  // Severity score from BSS
  const bss = vulnerability.bssScore?.totalScore || 0;
  const severityScore = bss / 10; // Normalize to 0-1

  // Composite score
  const compositeScore =
    EVOLUTION_CONFIG.noveltyWeight * noveltyScore +
    EVOLUTION_CONFIG.severityWeight * severityScore;

  return {
    noveltyScore: Math.round(noveltyScore * 100) / 100,
    severityScore: Math.round(severityScore * 100) / 100,
    compositeScore: Math.round(compositeScore * 100) / 100,
  };
}

/**
 * Batch score fitness for multiple vulnerabilities
 */
export async function batchScoreFitness(vulnerabilities, existingFindings, llm) {
  const scores = [];
  for (const vuln of vulnerabilities) {
    const score = await scoreFitness(vuln, existingFindings, llm);
    scores.push({
      vulnerabilityId: vuln._id,
      ...score,
    });
  }
  return scores;
}

/**
 * Natural selection — select top findings to feed into next generation
 */
export function selectForNextGeneration(vulnerabilities, fitnessScores) {
  const maxToSelect = EVOLUTION_CONFIG.maxFindingsToEvolve;
  const selectionRate = EVOLUTION_CONFIG.selectionRate;
  const minToSelect = EVOLUTION_CONFIG.minFindingsToEvolve;

  // Sort by composite score (descending)
  const sortedScores = [...fitnessScores].sort(
    (a, b) => b.compositeScore - a.compositeScore
  );

  // Select top N based on selection rate
  const targetCount = Math.max(
    minToSelect,
    Math.min(
      maxToSelect,
      Math.ceil(sortedScores.length * selectionRate)
    )
  );

  const selectedIds = sortedScores
    .slice(0, targetCount)
    .map((s) => s.vulnerabilityId);

  return selectedIds;
}
