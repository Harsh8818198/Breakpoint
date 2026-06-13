import connectDB from "@/lib/db/connect";
import Agent from "@/lib/db/models/Agent";
import Blueprint from "@/lib/db/models/Blueprint";
import { getLLMProviderWithFallback } from "@/lib/llm/factory";
import { getUserApiKey } from "@/lib/services/auth";
import { getAllArchetypes, getArchetype } from "@/lib/config/archetypes";
import { generateConstrainedLHS, measureDiversity } from "@/lib/services/lhsSampler";
import {
  getPersonaGenerationPrompt,
  getProductSpecificAgentsPrompt,
  getKnowledgeProfilePrompt,
} from "@/lib/prompts/agents/personaGeneration";
import { parallelWithLimit } from "@/lib/utils/helpers";
import { NotFoundError, ValidationError } from "@/lib/utils/errors";
import { LLM_CONCURRENCY, DIVERSITY_CONFIG } from "@/lib/config/constants";

/**
 * Generate a complete agent population for a simulation.
 */
export async function generateAgentPopulation(
  simulationId,
  blueprintId,
  config,
  userId,
  llmProvider
) {
  await connectDB();

  const blueprint = await Blueprint.findById(blueprintId);
  if (!blueprint) throw new NotFoundError("Blueprint");

  const apiKey = await getUserApiKey(userId, llmProvider);
  const llm = getLLMProviderWithFallback(llmProvider, apiKey);

  const totalAgents = config.totalAgents;
  const composition = config.agentComposition;
  const allAgents = [];

  // 1. Calculate agent counts per archetype
  const archetypeCounts = calculateArchetypeCounts(totalAgents, composition);

  // 2. Generate product-specific agent types from blueprint
  const productSpecificAgents = await generateProductSpecificAgents(llm, blueprint);

  // 3. Generate base archetype agents
  const archetypes = getAllArchetypes();
  const blueprintSummary = summarizeBlueprint(blueprint);

  for (const archetype of archetypes) {
    const count = archetypeCounts[archetype.id] || 0;
    if (count === 0) continue;

    // Generate LHS personality vectors constrained to archetype ranges
    const vectors = generateConstrainedLHS(count, archetype.personalityRanges);

    // Select and cycle through variants
    const variants = archetype.variants;

    // Generate personas in parallel (with rate limiting)
    const agentTasks = vectors.map((vector, index) => async () => {
      const variant = variants[index % variants.length];

      // Generate rich persona via LLM
      const personaPrompt = getPersonaGenerationPrompt(
        archetype,
        variant,
        blueprintSummary
      );
      const personaResult = await llm.chatJSON([
        { role: "user", content: personaPrompt },
      ]);

      // Generate knowledge profile
      const knowledgePrompt = getKnowledgeProfilePrompt(archetype, blueprint);
      const knowledgeResult = await llm.chatJSON([
        { role: "user", content: knowledgePrompt },
      ]);

      return {
        simulationId,
        persona: personaResult.data,
        archetypeId: archetype.id,
        archetypeName: archetype.name,
        variantType: variant.type,
        motivation: archetype.motivation,
        isCustom: false,
        isProductSpecific: false,
        knowledgeProfile: knowledgeResult.data,
        constraints: archetype.defaultConstraints,
        personalityVector: vector,
        generationsParticipated: [],
        findings: [],
      };
    });

    const results = await parallelWithLimit(
      agentTasks,
      LLM_CONCURRENCY[llmProvider] || 3
    );
    allAgents.push(...results);
  }

  // 4. Add product-specific agents
  for (const psAgent of productSpecificAgents) {
    const vector = generateConstrainedLHS(1, null)[0];

    allAgents.push({
      simulationId,
      persona: {
        name: psAgent.name,
        age: 25,
        background: psAgent.background,
        location: "Product-specific",
        occupation: "Product-specific agent",
      },
      archetypeId: psAgent.id,
      archetypeName: psAgent.name,
      variantType: "product_specific",
      motivation: psAgent.motivation,
      isCustom: false,
      isProductSpecific: true,
      knowledgeProfile: {
        knows: [],
        doesntKnow: [],
        domainExpertise: psAgent.whyRelevant,
      },
      constraints: psAgent.constraints || {},
      personalityVector: vector,
      generationsParticipated: [],
      findings: [],
    });
  }

  // 5. Add custom user-defined agents
  if (config.customAgents?.length) {
    for (const customAgent of config.customAgents) {
      const vector = generateConstrainedLHS(1, null)[0];

      allAgents.push({
        simulationId,
        persona: {
          name: `Custom Agent`,
          age: 30,
          background: customAgent.description,
          location: "Custom",
          occupation: "Custom scenario agent",
        },
        archetypeId: "custom",
        archetypeName: "Custom Agent",
        variantType: "custom",
        motivation: customAgent.scenario || customAgent.description,
        isCustom: true,
        isProductSpecific: false,
        knowledgeProfile: { knows: [], doesntKnow: [], domainExpertise: "" },
        constraints: {},
        personalityVector: vector,
        generationsParticipated: [],
        findings: [],
      });
    }
  }

  // 6. Save all agents to database
  const savedAgents = await Agent.insertMany(allAgents);

  // 7. Measure diversity
  const vectors = savedAgents.map((a) => a.personalityVector);
  const diversityScore = measureDiversity(vectors);

  return {
    agents: savedAgents.map((a) => a.toJSON()),
    stats: {
      total: savedAgents.length,
      archetypeBreakdown: archetypeCounts,
      productSpecificCount: productSpecificAgents.length,
      customCount: config.customAgents?.length || 0,
      diversityScore,
    },
  };
}

/**
 * Generate product-specific agent types from blueprint
 */
async function generateProductSpecificAgents(llm, blueprint) {
  try {
    const prompt = getProductSpecificAgentsPrompt(blueprint.toJSON());
    const result = await llm.chatJSON([{ role: "user", content: prompt }]);
    return result.data.productSpecificAgents || [];
  } catch {
    console.warn("Failed to generate product-specific agents, continuing without them");
    return [];
  }
}

/**
 * Calculate agent counts per archetype based on composition percentages
 */
function calculateArchetypeCounts(totalAgents, composition) {
  const counts = {};
  let assigned = 0;

  const entries = Object.entries(composition);

  for (let i = 0; i < entries.length; i++) {
    const [archetypeId, percentage] = entries[i];
    if (i === entries.length - 1) {
      // Last archetype gets the remainder to ensure total is exact
      counts[archetypeId] = totalAgents - assigned;
    } else {
      const count = Math.round((percentage / 100) * totalAgents);
      counts[archetypeId] = count;
      assigned += count;
    }
  }

  return counts;
}

/**
 * Summarize blueprint for agent context (keep it concise for prompts)
 */
function summarizeBlueprint(blueprint) {
  const bp = blueprint.toJSON ? blueprint.toJSON() : blueprint;
  return `Product: ${bp.identity?.name || "Unknown"} (${bp.identity?.type || "Unknown"})
Domain: ${bp.identity?.domain || "Unknown"}
Stage: ${bp.identity?.stage || "Unknown"}
Key Features: ${bp.attackSurfaceMap?.map((a) => a.feature).join(", ") || "N/A"}
User Types: ${bp.actors?.map((a) => a.name).join(", ") || "N/A"}
Key Boundaries: ${bp.boundaries?.map((b) => `${b.from} → ${b.to}`).join(", ") || "N/A"}`;
}

/**
 * Get agents for a simulation
 */
export async function getAgents(simulationId) {
  await connectDB();
  return Agent.find({ simulationId }).lean();
}
