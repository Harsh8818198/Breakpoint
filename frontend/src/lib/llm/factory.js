import { OpenAIProvider } from "./openai.js";
import { GeminiProvider } from "./gemini.js";
import { LLMError, ValidationError } from "@/lib/utils/errors";
import { LLM_PROVIDERS } from "@/lib/config/constants";

/**
 * LLM Provider instances cache - prevents creating multiple instances
 * with the same API key during a serverless function invocation
 */
const providerCache = new Map();

/**
 * Factory function to get an LLM provider instance.
 * 
 * @param {string} provider - "openai" or "gemini"
 * @param {string} apiKey - API key for the provider
 * @returns {BaseLLMProvider} - Configured provider instance
 */
export function getLLMProvider(provider, apiKey) {
  if (!provider || !Object.values(LLM_PROVIDERS).includes(provider)) {
    throw new ValidationError(
      `Invalid LLM provider: "${provider}". Must be "openai" or "gemini".`
    );
  }

  if (!apiKey) {
    throw new LLMError(
      provider,
      `No API key provided for ${provider}. Please set your API key in settings or environment variables.`
    );
  }

  // Cache key based on provider + key hash (don't cache full key)
  const cacheKey = `${provider}:${apiKey.slice(-8)}`;
  
  if (providerCache.has(cacheKey)) {
    return providerCache.get(cacheKey);
  }

  let instance;

  switch (provider) {
    case LLM_PROVIDERS.OPENAI:
      instance = new OpenAIProvider(apiKey);
      break;
    case LLM_PROVIDERS.GEMINI:
      instance = new GeminiProvider(apiKey);
      break;
    default:
      throw new ValidationError(`Unsupported LLM provider: ${provider}`);
  }

  providerCache.set(cacheKey, instance);
  return instance;
}

/**
 * Get the LLM provider for a specific user + project combination.
 * Resolves API key from user settings or environment variables.
 * 
 * @param {string} provider - "openai" or "gemini"
 * @param {string|null} userApiKey - User's stored API key (may be null)
 * @returns {BaseLLMProvider}
 */
export function getLLMProviderWithFallback(provider, userApiKey = null) {
  // Try user's key first, then fall back to env variable
  const apiKey =
    userApiKey ||
    (provider === "openai"
      ? process.env.OPENAI_API_KEY
      : process.env.GEMINI_API_KEY);

  return getLLMProvider(provider, apiKey);
}

/**
 * Clear the provider cache (useful for testing)
 */
export function clearProviderCache() {
  providerCache.clear();
}
