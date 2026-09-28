/**
 * Claim extraction prompt.
 * Takes a locked Product Blueprint and extracts the explicit and implicit
 * guarantees the product design makes — the unit that agents will target
 * instead of freeform archetype roleplay.
 */

export function getClaimExtractionPrompt(blueprint) {
  return `You are a security-minded product analyst. Read this Product Blueprint the way an AI safety evaluator reads a safety case: not "what could go wrong in general" but "what does this design specifically claim to guarantee, and what is the precise scenario where that claim is false?"

BLUEPRINT:
${JSON.stringify(blueprint, null, 2)}

Extract every guarantee the blueprint implies — from actor permissions, resource sensitivity, boundaries, flows, and mechanical details. A claim is a specific, falsifiable statement like "only the resource owner can read a private resource" or "crossing from Free tier to Paid tier requires the trigger condition to be met." Do not extract vague claims like "the system is secure."

For each claim, decide whether it is FORMALIZABLE: expressible as a predicate over actors/resources/state (e.g. \`access(actor, resource) => tenant(actor) == tenant(resource)\`). Business/UX claims that cannot be reduced to a predicate ("free users see upgrade prompts at the right time") are still valid claims — mark them not formalizable.

Return JSON in this exact structure:

{
  "claims": [
    {
      "statement": "Plain-language guarantee, one sentence",
      "category": "auth | rate_limit | data_isolation | payment | business_logic | ux | compliance | other",
      "featureRefs": ["names of actors/resources/boundaries/flows this claim depends on, as they appear in the blueprint"],
      "formalizable": true,
      "predicate": "short pseudo-logic expression if formalizable, else null",
      "severityIfFalse": "critical | high | medium | low"
    }
  ]
}

Extract as many distinct, falsifiable claims as the blueprint supports — typically 15-40 for a moderately complex product. Prefer specific over general. Every attackSurfaceMap entry and every boundary should yield at least one claim.`;
}
