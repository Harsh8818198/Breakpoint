/**
 * General utility functions for Breakpoint
 */

/**
 * Parse JSON body from request, with error handling
 */
export async function parseBody(request) {
  try {
    const body = await request.json();
    return body;
  } catch {
    return null;
  }
}

/**
 * Extract query parameters from URL
 */
export function getQueryParams(request) {
  const { searchParams } = new URL(request.url);
  return Object.fromEntries(searchParams.entries());
}

/**
 * Generate a unique ID string
 */
export function generateId() {
  return crypto.randomUUID();
}

/**
 * Sleep for specified milliseconds
 */
export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Retry an async function with exponential backoff
 */
export async function retryWithBackoff(fn, maxRetries = 3, baseDelay = 1000) {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (attempt === maxRetries) throw error;
      const delay = baseDelay * Math.pow(2, attempt) + Math.random() * 1000;
      await sleep(delay);
    }
  }
}

/**
 * Chunk an array into smaller arrays of specified size
 */
export function chunkArray(array, size) {
  const chunks = [];
  for (let i = 0; i < array.length; i += size) {
    chunks.push(array.slice(i, i + size));
  }
  return chunks;
}

/**
 * Run promises in parallel with concurrency limit
 */
export async function parallelWithLimit(tasks, limit = 5) {
  const results = [];
  const executing = new Set();

  for (const task of tasks) {
    const p = Promise.resolve().then(() => task());
    results.push(p);
    executing.add(p);

    const clean = () => executing.delete(p);
    p.then(clean, clean);

    if (executing.size >= limit) {
      await Promise.race(executing);
    }
  }

  return Promise.all(results);
}

/**
 * Calculate cosine similarity between two vectors
 */
export function cosineSimilarity(vecA, vecB) {
  if (vecA.length !== vecB.length) {
    throw new Error("Vectors must have the same length");
  }

  let dotProduct = 0;
  let normA = 0;
  let normB = 0;

  for (let i = 0; i < vecA.length; i++) {
    dotProduct += vecA[i] * vecB[i];
    normA += vecA[i] * vecA[i];
    normB += vecB[i] * vecB[i];
  }

  normA = Math.sqrt(normA);
  normB = Math.sqrt(normB);

  if (normA === 0 || normB === 0) return 0;

  return dotProduct / (normA * normB);
}

/**
 * Truncate text to max length
 */
export function truncate(text, maxLength = 200) {
  if (!text || text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}

/**
 * Safely parse JSON string, returns null on failure
 */
export function safeParseJSON(str) {
  try {
    return JSON.parse(str);
  } catch {
    return null;
  }
}

/**
 * Extract JSON from LLM response that may contain markdown code blocks
 */
export function extractJSONFromLLM(text) {
  // Try direct parse first
  const direct = safeParseJSON(text);
  if (direct) return direct;

  // Try extracting from code blocks
  const codeBlockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  if (codeBlockMatch) {
    return safeParseJSON(codeBlockMatch[1].trim());
  }

  // Try finding JSON-like content
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    return safeParseJSON(jsonMatch[0]);
  }

  return null;
}

/**
 * Clamp a number between min and max
 */
export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
