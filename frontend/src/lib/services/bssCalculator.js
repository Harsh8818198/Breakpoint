import { getBSSSeverity } from "@/lib/config/constants";

/**
 * Calculate Breakpoint Severity Score (BSS) for a vulnerability.
 * BSS = (Exploitability × Impact × Spread) / Fix Difficulty
 */
export async function calculateBSS(vulnerabilityData, llm) {
  const prompt = `Rate this vulnerability on four dimensions. Be objective and realistic.

VULNERABILITY:
Title: ${vulnerabilityData.title}
Description: ${vulnerabilityData.description}
Steps to exploit: ${vulnerabilityData.stepsToExploit?.join(", ") || "N/A"}
Category: ${vulnerabilityData.category}
Target feature: ${vulnerabilityData.targetFeature}

Rate each dimension (0-10 scale):

1. EXPLOITABILITY (0-10): How easy is it for a TYPICAL user (not an expert) to exploit this?
   0 = requires expert technical skills | 10 = anyone could do it accidentally

2. IMPACT (0-10): What's the total damage? (revenue loss + reputation damage + user harm)
   0 = negligible | 10 = company-threatening

3. SPREAD (0-10): How viral is this exploit? Will users share it with others?
   0 = kept private | 10 = would go viral immediately

4. FIX DIFFICULTY (1-10): How hard is it to fix? (1 = trivial fix, 10 = requires major rearchitecture)
   Note: this is the DENOMINATOR, so higher = lower BSS score

Respond in JSON:
{
  "exploitability": number,
  "impact": number,
  "spread": number,
  "fixDifficulty": number,
  "reasoning": "Brief justification for each score"
}`;

  const result = await llm.chatJSON([{ role: "user", content: prompt }]);
  const scores = result.data;

  // Clamp values
  const exploitability = Math.max(0, Math.min(10, scores.exploitability || 0));
  const impact = Math.max(0, Math.min(10, scores.impact || 0));
  const spread = Math.max(0, Math.min(10, scores.spread || 0));
  const fixDifficulty = Math.max(1, Math.min(10, scores.fixDifficulty || 5));

  // Calculate BSS
  const totalScore = Math.round(
    ((exploitability * impact * spread) / fixDifficulty / 100) * 100
  ) / 100;

  return {
    exploitability,
    impact,
    spread,
    fixDifficulty,
    totalScore,
    severity: getBSSSeverity(totalScore),
  };
}

/**
 * Calculate BSS without LLM (using estimated values from vulnerability data)
 */
export function estimateBSS(vulnerabilityData) {
  // Heuristic estimation when we don't want to spend an LLM call
  const impact = vulnerabilityData.estimatedImpact;
  
  const viralityMap = { high: 8, medium: 5, low: 2 };
  const spread = viralityMap[impact?.virality] || 5;
  
  const exploitability = (vulnerabilityData.stepsToExploit?.length || 3) <= 3 ? 7 : 4;
  const impactScore = 6; // Default moderate impact
  const fixDifficulty = 5; // Default moderate difficulty

  const totalScore = Math.round(
    ((exploitability * impactScore * spread) / fixDifficulty / 100) * 100
  ) / 100;

  return {
    exploitability,
    impact: impactScore,
    spread,
    fixDifficulty,
    totalScore,
    severity: getBSSSeverity(totalScore),
  };
}
