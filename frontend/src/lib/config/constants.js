/**
 * App-wide constants for Breakpoint V2
 */

// Blueprint
export const MAX_REFINEMENT_CYCLES = 3;
export const MAX_FOLLOWUP_ROUNDS = 3;

// Simulation Intensity Presets
export const INTENSITY_PRESETS = {
  light: {
    name: "Light",
    totalAgents: 20,
    totalGenerations: 3,
    estimatedLlmCalls: 60,
    estimatedDuration: "~2 minutes",
  },
  standard: {
    name: "Standard",
    totalAgents: 50,
    totalGenerations: 5,
    estimatedLlmCalls: 127,
    estimatedDuration: "~4 minutes",
  },
  deep: {
    name: "Deep",
    totalAgents: 100,
    totalGenerations: 7,
    estimatedLlmCalls: 250,
    estimatedDuration: "~8 minutes",
  },
  adversarial: {
    name: "Adversarial",
    totalAgents: 200,
    totalGenerations: 10,
    estimatedLlmCalls: 500,
    estimatedDuration: "~15 minutes",
  },
};

// Agent Archetype IDs
export const ARCHETYPE_IDS = {
  FREELOADER: "freeloader",
  GUARDIAN: "guardian",
  HACKER: "hacker",
  ORGANIZER: "organizer",
  POWER_USER: "power_user",
  CRITIC: "critic",
  COMPETITOR: "competitor",
  GRIEFER: "griefer",
  NAIVE_USER: "naive_user",
  REGULATOR: "regulator",
  SCALPER: "scalper",
  ADVOCATE: "advocate",
};

// Personality Vector Dimensions
export const PERSONALITY_DIMENSIONS = [
  "frugality",
  "techSavviness",
  "patience",
  "socialInfluence",
  "riskTolerance",
  "privacyConsciousness",
  "ethicalFlexibility",
  "persistence",
];

// BSS (Breakpoint Severity Score) Thresholds
export const BSS_THRESHOLDS = {
  CRITICAL: 7.0,
  HIGH: 4.0,
  MEDIUM: 2.0,
  LOW: 0,
};

export function getBSSSeverity(score) {
  if (score >= BSS_THRESHOLDS.CRITICAL) return "critical";
  if (score >= BSS_THRESHOLDS.HIGH) return "high";
  if (score >= BSS_THRESHOLDS.MEDIUM) return "medium";
  return "low";
}

// Generation Themes
export const GENERATION_THEMES = {
  1: {
    name: "Individual Feature Probing",
    focus: "individual_probing",
    description: "Wide, shallow — each agent probes one feature",
  },
  2: {
    name: "Combinatorial Attacks",
    focus: "combinatorial",
    description: "Combine Gen 1 findings into cross-feature exploits",
  },
  3: {
    name: "Systemic/Organized Attacks",
    focus: "systemic",
    description: "Scale + coordination — organized group exploitation",
  },
  4: {
    name: "Business Impact Analysis",
    focus: "business_impact",
    description: "Second-order effects — revenue, reputation, trust",
  },
  5: {
    name: "Novel/Emergent Attacks",
    focus: "emergent",
    description: "Temporal, cascade, and meta-exploits",
  },
};

// Focus Areas
export const FOCUS_AREAS = {
  pricing: {
    name: "Pricing & Revenue",
    description: "How users avoid paying",
    icon: "💰",
  },
  privacy: {
    name: "Privacy & Data",
    description: "How data is exposed or misused",
    icon: "🔒",
  },
  security: {
    name: "Security & Auth",
    description: "How access controls are bypassed",
    icon: "🛡️",
  },
  ux: {
    name: "UX & Adoption",
    description: "Where users get confused or drop off",
    icon: "🎨",
  },
  social: {
    name: "Social & Abuse",
    description: "How users harm each other or the platform",
    icon: "👥",
  },
  reputation: {
    name: "Reputation & Trust",
    description: "How the platform's image is damaged",
    icon: "⭐",
  },
  compliance: {
    name: "Compliance & Legal",
    description: "Regulatory and legal risks",
    icon: "⚖️",
  },
  competitive: {
    name: "Competitive & IP",
    description: "How competitors could exploit this",
    icon: "🏢",
  },
};

// Project Statuses
export const PROJECT_STATUS = {
  INTAKE: "intake",
  VERIFICATION: "verification",
  READY: "ready",
  SIMULATING: "simulating",
  COMPLETED: "completed",
};

// Blueprint Statuses
export const BLUEPRINT_STATUS = {
  DRAFT: "draft",
  UNDER_REVIEW: "under_review",
  LOCKED: "locked",
};

// Simulation Statuses
export const SIMULATION_STATUS = {
  CONFIGURING: "configuring",
  GENERATING_AGENTS: "generating_agents",
  RUNNING: "running",
  PAUSED: "paused",
  COMPLETED: "completed",
  FAILED: "failed",
};

// Intake Modes
export const INTAKE_MODES = {
  CONVERSATION: "conversation",
  DOCUMENT: "document",
  CODEBASE: "codebase",
};

// LLM Providers
export const LLM_PROVIDERS = {
  OPENAI: "openai",
  GEMINI: "gemini",
};

// Agent diversity constraints
export const DIVERSITY_CONFIG = {
  MIN_DISTANCE_DIMENSIONS: 2, // No two agents close in more than 2 dims
  SIMILARITY_THRESHOLD: 0.85, // Dedup threshold for cosine similarity
  PRODUCT_SPECIFIC_AGENT_COUNT: { min: 5, max: 10 },
  VARIANTS_PER_ARCHETYPE: { min: 3, max: 5 },
};

// LLM Concurrency (to avoid rate limits)
export const LLM_CONCURRENCY = {
  openai: 5,
  gemini: 3,
};
