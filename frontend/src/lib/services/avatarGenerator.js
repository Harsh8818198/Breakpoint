import { getLLMProviderWithFallback } from "@/lib/llm/factory";
import { getUserApiKey } from "@/lib/services/auth";
import { LLMError } from "@/lib/utils/errors";

/**
 * Generate an AI avatar for an agent persona
 */
export async function generateAvatar(persona, userId, llmProvider) {
  const apiKey = await getUserApiKey(userId, llmProvider);
  const llm = getLLMProviderWithFallback(llmProvider, apiKey);

  const prompt = `A professional portrait illustration of ${persona.name}, ${persona.age} years old, ${persona.occupation}. ${persona.background?.split(".")[0] || ""}. Style: modern, clean, minimal vector illustration with solid background. NO text, NO labels, NO watermarks. Just the face/bust portrait.`;

  try {
    const result = await llm.generateImage(prompt, {
      size: "256x256",
      quality: "standard",
    });
    return result.url || result.base64;
  } catch (error) {
    console.warn(`Avatar generation failed for ${persona.name}: ${error.message}`);
    // Return null — avatar is optional
    return null;
  }
}

/**
 * Generate avatars for a batch of agents
 */
export async function generateAvatarBatch(agents, userId, llmProvider, concurrency = 2) {
  const results = [];
  
  for (let i = 0; i < agents.length; i += concurrency) {
    const batch = agents.slice(i, i + concurrency);
    const batchResults = await Promise.allSettled(
      batch.map((agent) => generateAvatar(agent.persona, userId, llmProvider))
    );
    
    results.push(
      ...batchResults.map((r) =>
        r.status === "fulfilled" ? r.value : null
      )
    );
  }

  return results;
}
