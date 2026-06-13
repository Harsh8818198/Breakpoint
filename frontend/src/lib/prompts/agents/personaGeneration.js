/**
 * Agent persona generation prompts
 */

export function getPersonaGenerationPrompt(archetype, variant, blueprintSummary) {
  return `Generate a rich, realistic persona for a simulated user agent.

ARCHETYPE: ${archetype.name}
VARIANT: ${variant.type} — ${variant.seed}
PRODUCT CONTEXT: ${blueprintSummary}

Generate a complete persona in JSON format:
{
  "name": "A realistic full name (culturally appropriate for the product's target market)",
  "age": number between 16 and 60,
  "background": "A 3-4 sentence rich backstory. Include their daily life, habits, social circles, and relationship with technology. Make this feel like a REAL person, not a parameter vector.",
  "location": "City, Country",
  "occupation": "Their job or role"
}

RULES:
- The persona should feel REAL — someone you could meet in real life
- The background should naturally explain WHY they would behave the way their archetype suggests
- Include specific details (Telegram groups, subreddits, habits) that make the persona vivid
- The persona should be appropriate for someone who would actually use this product
- Vary demographics — don't make everyone a 22-year-old CS student`;
}

export function getProductSpecificAgentsPrompt(blueprint) {
  return `You are generating product-specific threat agent types for adversarial simulation.

PRODUCT BLUEPRINT:
${JSON.stringify(blueprint, null, 2)}

Based on this SPECIFIC product and its domain, generate 5-8 additional agent types that are UNIQUE to this product. These should represent realistic threat actors who would be specific to this product category.

For example:
- For an EdTech app: "The Exam Cheater", "The TA Exploiter", "The Note Seller"
- For a marketplace: "The Fake Reviewer", "The Price Manipulator"
- For a social app: "The Catfish", "The Influence Farmer"

Respond in JSON:
{
  "productSpecificAgents": [
    {
      "id": "snake_case_unique_id",
      "name": "The [Name]",
      "goal": "What they're trying to achieve",
      "motivation": "Detailed motivation text",
      "background": "A rich backstory for this agent type",
      "constraints": {
        "willingTo": ["specific actions"],
        "unwillingTo": ["limits"],
        "techSkillLevel": "novice|intermediate|advanced|expert"
      },
      "whyRelevant": "Why this agent type matters for THIS specific product"
    }
  ]
}`;
}

export function getKnowledgeProfilePrompt(archetype, blueprint) {
  return `Generate a domain-specific knowledge profile for this agent type.

AGENT TYPE: ${archetype.name} — ${archetype.goal}
PRODUCT DOMAIN: ${blueprint.identity?.domain || "General"}

What would this type of person realistically KNOW and NOT KNOW about:
1. The product's domain (e.g., EdTech, FinTech)
2. Technical systems
3. Common exploits in this domain

Respond in JSON:
{
  "knows": ["List of things this person would realistically know about"],
  "doesntKnow": ["Things they wouldn't know"],
  "domainExpertise": "Brief description of their domain knowledge level"
}`;
}
