/**
 * Default simulation configuration for Breakpoint
 */

import { INTENSITY_PRESETS, ARCHETYPE_IDS } from "./constants.js";

/**
 * Default agent composition percentages (must sum to 100)
 */
export const DEFAULT_AGENT_COMPOSITION = {
  [ARCHETYPE_IDS.FREELOADER]: 15,
  [ARCHETYPE_IDS.GUARDIAN]: 10,
  [ARCHETYPE_IDS.HACKER]: 10,
  [ARCHETYPE_IDS.ORGANIZER]: 8,
  [ARCHETYPE_IDS.POWER_USER]: 10,
  [ARCHETYPE_IDS.CRITIC]: 8,
  [ARCHETYPE_IDS.COMPETITOR]: 5,
  [ARCHETYPE_IDS.GRIEFER]: 5,
  [ARCHETYPE_IDS.NAIVE_USER]: 12,
  [ARCHETYPE_IDS.REGULATOR]: 5,
  [ARCHETYPE_IDS.SCALPER]: 5,
  [ARCHETYPE_IDS.ADVOCATE]: 7,
};

/**
 * Default simulation settings
 */
export const DEFAULT_SIMULATION_CONFIG = {
  intensity: "standard",
  ...INTENSITY_PRESETS.standard,
  focusAreas: [
    "pricing",
    "privacy",
    "security",
    "ux",
    "social",
    "reputation",
    "compliance",
    "competitive",
  ],
  agentComposition: DEFAULT_AGENT_COMPOSITION,
  customAgents: [],
};

/**
 * Default LLM settings per provider
 */
export const DEFAULT_LLM_SETTINGS = {
  openai: {
    chatModel: "gpt-4o",
    embeddingModel: "text-embedding-3-small",
    imageModel: "dall-e-3",
    maxTokens: 4096,
    temperature: 0.7,
  },
  gemini: {
    chatModel: "gemma-4-31b-it",
    embeddingModel: "text-embedding-004",
    imageModel: "imagen-3.0-generate-002",
    maxTokens: 4096,
    temperature: 0.7,
  },
};

/**
 * Default BSS scoring weights
 */
export const DEFAULT_BSS_WEIGHTS = {
  exploitability: 1.0,
  impact: 1.0,
  spread: 1.0,
  fixDifficulty: 1.0,
};

/**
 * Deduplication settings
 */
export const DEDUP_CONFIG = {
  similarityThreshold: 0.85,
  maxClusterSize: 5,
  keepStrategy: "highest_quality", // "highest_quality" | "first_found"
};

/**
 * Evolution selection settings
 */
export const EVOLUTION_CONFIG = {
  // What percentage of findings from gen N feed into gen N+1
  selectionRate: 0.6,
  // Minimum findings required to proceed to next generation
  minFindingsToEvolve: 3,
  // Maximum findings to feed forward (to keep context manageable)
  maxFindingsToEvolve: 15,
  // Novelty weight in fitness score
  noveltyWeight: 0.6,
  // Severity weight in fitness score
  severityWeight: 0.4,
};
