/**
 * Blueprint generation master prompt.
 * Takes raw data from any intake mode and produces the standardized Product Blueprint.
 */

export function getBlueprintGenerationPrompt(sourceData) {
  return `You are a product analyst generating a comprehensive Product Blueprint for adversarial simulation testing.

SOURCE DATA:
${JSON.stringify(sourceData, null, 2)}

Generate a complete Product Blueprint in the following JSON structure. Be thorough — every detail matters for the quality of the vulnerability simulation.

{
  "identity": {
    "name": "Product name",
    "type": "SaaS web application / mobile app / API / marketplace / etc.",
    "domain": "EdTech / FinTech / HealthTech / SocialMedia / etc.",
    "stage": "pre_launch | beta | live"
  },
  
  "actors": [
    {
      "name": "Actor name (e.g., 'Free-tier Student')",
      "role": "Their role in the system",
      "description": "What they do, their access level",
      "permissions": ["list", "of", "what they can do"]
    }
  ],
  
  "resources": [
    {
      "name": "Resource name (e.g., 'User Accounts', 'AI-Generated Content')",
      "type": "data | content | feature | service",
      "description": "What this resource is",
      "ownership": "Who owns/controls this resource",
      "sensitivity": "public | private | sensitive"
    }
  ],
  
  "boundaries": [
    {
      "from": "State A (e.g., 'Free tier')",
      "to": "State B (e.g., 'Paid tier')",
      "trigger": "What causes the transition (e.g., '5 questions/day limit reached')",
      "description": "Details about this boundary"
    }
  ],
  
  "flows": [
    {
      "name": "Flow name (e.g., 'User Signup')",
      "steps": [
        {"order": 1, "action": "What happens", "actor": "Who does it", "details": "Specifics"}
      ],
      "edgeCases": ["What could go wrong or be exploited at each step"]
    }
  ],
  
  "mechanicalDetails": [
    {
      "feature": "Feature name",
      "detail": "Specific mechanical detail (e.g., 'Rate limit resets at midnight UTC')",
      "status": "confirmed | assumed | unknown"
    }
  ],
  
  "knownUnknowns": [
    {
      "question": "Specific question about undefined behavior",
      "relevance": "Why this matters for security/exploitation",
      "attackPotential": "high | medium | low"
    }
  ],
  
  "attackSurfaceMap": [
    {
      "feature": "Feature name",
      "riskLevel": "critical | high | medium | low",
      "attackVectors": ["How this could be exploited"],
      "relatedBoundaries": ["Which boundaries this connects to"]
    }
  ],
  
  "preSimulationRisks": [
    {
      "title": "Risk title",
      "description": "Why this is risky — what you can already see before simulation",
      "severity": "critical | high | medium | low"
    }
  ],
  
  "assumptions": [
    {
      "statement": "Something assumed but not confirmed",
      "userVerified": false
    }
  ]
}

RULES:
1. Be SPECIFIC — avoid generic statements. Every item should reference actual product features.
2. STRICT ENUMS: You MUST only use the exact values provided for the following fields: 
   - identity.stage: "pre_launch", "beta", "live", or "" (empty string)
   - resources.sensitivity: "public", "private", "sensitive"
   - mechanicalDetails.status: "confirmed", "assumed", "unknown"
   - knownUnknowns.attackPotential: "high", "medium", "low"
   - attackSurfaceMap.riskLevel: "critical", "high", "medium", "low"
   - preSimulationRisks.severity: "critical", "high", "medium", "low"
3. DATA TYPES: Every field in an array (like actors, resources, flows) MUST be the full object specified in the template, never just a string.
4. Known Unknowns are HIGH PRIORITY — undefined behavior is the most exploitable behavior.
5. Include at least 3 actors, 3 boundaries, 3 flows, 5 mechanical details, 5 known unknowns.
6. The blueprint should give agents enough detail to find genuinely different things at each generation.`;
}

/**
 * Verification presentation prompt — formats blueprint for user review
 */
export function getVerificationPrompt(blueprint) {
  return `You are presenting a Product Blueprint back to a founder for verification.

BLUEPRINT:
${JSON.stringify(blueprint, null, 2)}

Generate a human-readable verification presentation in JSON format:

{
  "coreProduct": {
    "summary": "2-3 sentence natural language description of what the product is",
    "isCorrect": null
  },
  "userAccessModel": {
    "summary": "How users access the product — auth, tiers, permissions",
    "isCorrect": null
  },
  "keyFeatures": [
    {"feature": "Feature name", "understanding": "How we understand this feature works", "isCorrect": null}
  ],
  "assumptions": [
    {"statement": "What we're assuming", "question": "Is this correct?", "isCorrect": null}
  ],
  "risksAlreadyVisible": [
    {"title": "Risk title", "description": "What we can already see is risky", "severity": "critical|high|medium|low"}
  ],
  "questionForUser": "Any final question for the user before proceeding"
}

Make the language conversational and clear — the founder should immediately understand what you think their product is and whether you got it right.`;
}

/**
 * Risk preview prompt — quick identification of 3-5 immediate risks
 */
export function getRiskPreviewPrompt(blueprint) {
  return `You are an adversarial product analyst. Given this Product Blueprint, identify 3-5 risks that are IMMEDIATELY visible — things you can spot in 10 seconds without running a full simulation.

BLUEPRINT:
${JSON.stringify(blueprint, null, 2)}

For each risk, explain:
1. What the risk is
2. Why it's exploitable
3. A one-sentence "If I were a user, I would..." scenario

Respond in JSON format:
{
  "risks": [
    {
      "title": "Short risk name",
      "description": "What the risk is and why it matters",
      "exploitScenario": "If I were a user, I would...",
      "severity": "critical | high | medium | low",
      "affectedFeature": "Which product feature this relates to"
    }
  ],
  "overallRiskLevel": "critical | high | medium | low",
  "urgentMessage": "One sentence telling the founder the most important thing"
}`;
}
