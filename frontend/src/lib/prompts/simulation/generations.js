/**
 * Generation-specific prompts for the evolutionary simulation engine.
 * Each generation asks fundamentally DIFFERENT questions — this is the core mechanism
 * that guarantees Gen 1 ≠ Gen 5.
 */

export function getGen1Prompt(persona, blueprint) {
  return `You are ${persona.persona.name}. ${persona.persona.background}

YOUR MOTIVATION: ${persona.motivation}

You've just discovered this product for the first time:

PRODUCT: ${blueprint.identity?.name}
TYPE: ${blueprint.identity?.type}

FEATURES & ATTACK SURFACES:
${blueprint.attackSurfaceMap?.map((a) => `- ${a.feature} (Risk: ${a.riskLevel}): ${a.attackVectors?.join(", ")}`).join("\n") || "N/A"}

USER FLOWS:
${blueprint.flows?.map((f) => `- ${f.name}: ${f.steps?.map((s) => s.action).join(" → ")}`).join("\n") || "N/A"}

BOUNDARIES:
${blueprint.boundaries?.map((b) => `- ${b.from} → ${b.to}: ${b.trigger}`).join("\n") || "N/A"}

KNOWN UNKNOWNS:
${blueprint.knownUnknowns?.map((k) => `- ${k.question} (Attack potential: ${k.attackPotential})`).join("\n") || "N/A"}

Based on who you are, your personality, and your goals — what's the FIRST thing you notice that could be exploited or that bothers you? Think about your immediate, gut-level reaction as ${persona.persona.name}.

CONSTRAINTS:
- Reference ONLY direct product features (don't make up features that aren't listed)
- Provide ONE specific, actionable vulnerability
- Think from YOUR persona's perspective — what would YOU specifically do?

Respond in JSON:
{
  "title": "Short vulnerability name",
  "description": "2-3 sentences describing the vulnerability",
  "stepsToExploit": ["Step 1", "Step 2", "Step 3"],
  "category": "pricing|privacy|security|ux|social|reputation|compliance|competitive",
  "targetFeature": "Which product feature this targets",
  "reasoning": "Why this specific persona would find and care about this vulnerability",
  "estimatedImpact": {
    "revenue": "How this affects revenue",
    "reputation": "How this affects reputation",
    "exploitRate": "What percentage of users like you would find this",
    "virality": "high|medium|low"
  },
  "suggestedFix": "How the product should fix this"
}`;
}

export function getGen2Prompt(persona, blueprint, gen1Findings) {
  const findingsList = gen1Findings
    .map((f, i) => `${i + 1}. "${f.title}" — ${f.description} (Found by: ${f.discoveredByName || "another user"})`)
    .join("\n");

  return `You are ${persona.persona.name}. ${persona.persona.background}

YOUR MOTIVATION: ${persona.motivation}

You've been using ${blueprint.identity?.name} for a week now. You've heard from other users about these issues:

DISCOVERED ISSUES:
${findingsList}

PRODUCT DETAILS:
${blueprint.attackSurfaceMap?.map((a) => `- ${a.feature}: ${a.attackVectors?.join(", ")}`).join("\n") || "N/A"}

Based on your personality, how would you COMBINE or EXTEND these discoveries? What new exploit emerges when you put two or more of these together?

CONSTRAINTS:
- MUST reference at least 2 of the Gen 1 findings above
- MUST produce something DIFFERENT from any individual finding
- Think about INTERACTIONS between features, not just single features
- The combined exploit should be MORE dangerous than either parent alone

Respond in JSON:
{
  "title": "Short name for the combined vulnerability",
  "description": "2-3 sentences describing the NEW combined vulnerability",
  "stepsToExploit": ["Step 1", "Step 2", "Step 3", "Step 4"],
  "category": "pricing|privacy|security|ux|social|reputation|compliance|competitive",
  "targetFeature": "Primary feature targeted",
  "parentFindings": ["Title of parent finding 1", "Title of parent finding 2"],
  "reasoning": "How combining these findings creates a new, more dangerous exploit",
  "estimatedImpact": {
    "revenue": "Revenue impact",
    "reputation": "Reputation impact",
    "exploitRate": "Estimated exploit rate",
    "virality": "high|medium|low"
  },
  "suggestedFix": "How to fix this combined vulnerability"
}`;
}

export function getGen3Prompt(persona, blueprint, previousFindings) {
  const findingsList = previousFindings
    .map((f, i) => `${i + 1}. [Gen ${f.generationNumber}] "${f.title}" — ${f.description}`)
    .join("\n");

  return `You are ${persona.persona.name}. ${persona.persona.background}

YOUR MOTIVATION: ${persona.motivation}

You're part of a community of users who have been using ${blueprint.identity?.name} for months.
The community has discovered these vulnerabilities:

ALL KNOWN ISSUES:
${findingsList}

What SYSTEMIC exploit would emerge if these were widely known? How would ORGANIZED GROUPS take advantage?

CONSTRAINTS:
- Must consider SCALE — what happens when 100+ users exploit this simultaneously?
- Must consider COORDINATION — how would a WhatsApp group or Discord server organize this?
- Must produce something that requires MULTIPLE PEOPLE working together
- Think about the SOCIAL DYNAMICS of exploitation

Respond in JSON:
{
  "title": "Name for the systemic/organized exploit",
  "description": "Description of the organized exploitation pattern",
  "stepsToExploit": ["Step 1", "Step 2", "Step 3", "Step 4", "Step 5"],
  "category": "pricing|privacy|security|ux|social|reputation|compliance|competitive",
  "targetFeature": "Primary feature targeted",
  "parentFindings": ["Related parent findings"],
  "reasoning": "How scale and coordination make this qualitatively different",
  "organizationRequired": "How many people and what coordination is needed",
  "estimatedImpact": {
    "revenue": "Revenue impact at scale",
    "reputation": "Reputation damage from organized exploitation",
    "exploitRate": "What percentage of the user base could participate",
    "virality": "high|medium|low"
  },
  "suggestedFix": "How to fix this systemic issue"
}`;
}

export function getGen4Prompt(persona, blueprint, previousFindings) {
  const findingsList = previousFindings
    .map((f, i) => `${i + 1}. [Gen ${f.generationNumber}] "${f.title}" (${f.bssScore?.severity || "unknown"}) — ${f.description}`)
    .join("\n");

  return `You are ${persona.persona.name}. ${persona.persona.background}

You're analyzing ${blueprint.identity?.name} from a MARKET and BUSINESS perspective.

Given these known vulnerabilities:
${findingsList}

What are the BUSINESS CONSEQUENCES? Think about:
- Revenue loss (how much money does the company lose?)
- Reputation damage (what happens to user trust and public perception?)
- Competitive advantage loss (how do competitors benefit?)
- Regulatory/legal exposure (could this trigger legal action?)
- Cascade effects (how does one problem lead to another?)

CONSTRAINTS:
- Focus on SECOND-ORDER effects — not the exploit itself, but what happens BECAUSE of it
- Think about TIME — what happens over 30/60/90 days?
- Consider the MARKET — what would competitors do with this information?

Respond in JSON:
{
  "title": "Name for the business impact vulnerability",
  "description": "Description of the business-level consequence",
  "stepsToExploit": ["How this plays out over time"],
  "category": "pricing|privacy|security|ux|social|reputation|compliance|competitive",
  "targetFeature": "Primary business area affected",
  "parentFindings": ["Vulnerabilities that lead to this consequence"],
  "reasoning": "Why this business consequence is likely given the vulnerabilities",
  "businessImpact": {
    "revenueImpact": "Estimated financial impact (₹ or % of revenue)",
    "timeToImpact": "How long until this becomes visible",
    "recoveryDifficulty": "How hard is it to recover from this damage",
    "competitorAdvantage": "How competitors benefit"
  },
  "estimatedImpact": {
    "revenue": "Detailed revenue impact",
    "reputation": "Detailed reputation impact",
    "exploitRate": "N/A for business impact",
    "virality": "high|medium|low"
  },
  "suggestedFix": "Strategic recommendation to prevent this business outcome"
}`;
}

export function getGen5Prompt(persona, blueprint, allFindings) {
  const findingsList = allFindings
    .map((f, i) => `${i + 1}. [Gen ${f.generationNumber}] "${f.title}" — ${f.description}`)
    .join("\n");

  return `You are ${persona.persona.name}. ${persona.persona.background}

You know EVERYTHING that previous agents have discovered about ${blueprint.identity?.name}:

COMPLETE VULNERABILITY LANDSCAPE:
${findingsList}

PRODUCT BLUEPRINT:
Features: ${blueprint.attackSurfaceMap?.map((a) => a.feature).join(", ") || "N/A"}
Boundaries: ${blueprint.boundaries?.map((b) => `${b.from}→${b.to}`).join(", ") || "N/A"}
Known Unknowns: ${blueprint.knownUnknowns?.map((k) => k.question).join("; ") || "N/A"}

Find the ONE vulnerability that NOBODY else found. The thing that's hiding in the interaction between 3+ features, that only becomes visible when you understand the full picture.

Think about:
- TEMPORAL attacks: exploits that work over time (like slowly poisoning data)
- CASCADE failures: one exploit automatically enabling another
- META-EXPLOITS: exploiting the FIX for a previous exploit
- EMERGENT behavior: what happens when many users do slightly different things simultaneously
- NOVEL combinations that weren't covered by Gen 1-4

CONSTRAINTS:
- Must be genuinely NOVEL — if it's a restatement of any previous finding, it fails
- Must reference at least 3 features or systems interacting
- Must explain why this wasn't discoverable at earlier generations

Respond in JSON:
{
  "title": "Name for the novel vulnerability",
  "description": "Description of this non-obvious, emergent vulnerability",
  "stepsToExploit": ["Detailed steps showing the multi-feature interaction"],
  "category": "pricing|privacy|security|ux|social|reputation|compliance|competitive",
  "targetFeature": "Primary features involved",
  "parentFindings": ["All findings this builds upon"],
  "reasoning": "Why this required full vulnerability landscape knowledge to discover",
  "noveltyExplanation": "What makes this genuinely different from all previous findings",
  "estimatedImpact": {
    "revenue": "Revenue impact",
    "reputation": "Reputation impact",
    "exploitRate": "Estimated exploit rate",
    "virality": "high|medium|low"
  },
  "suggestedFix": "How to address this systemic vulnerability"
}`;
}

/**
 * Get the appropriate generation prompt
 */
export function getGenerationPrompt(genNumber) {
  const prompts = { 1: getGen1Prompt, 2: getGen2Prompt, 3: getGen3Prompt, 4: getGen4Prompt, 5: getGen5Prompt };
  return prompts[genNumber] || prompts[5]; // Gen 6+ uses Gen 5 prompt
}
