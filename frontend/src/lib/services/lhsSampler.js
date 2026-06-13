/**
 * Latin Hypercube Sampling (LHS) implementation for Breakpoint.
 * Guarantees diverse agent personality vectors across all 8 dimensions.
 */

import { PERSONALITY_DIMENSIONS } from "@/lib/config/constants";

/**
 * Generate a Latin Hypercube Sample.
 * 
 * @param {number} n - Number of samples (agents)
 * @param {number} d - Number of dimensions (8 for personality vector)
 * @param {Object} ranges - Optional per-dimension ranges { dimName: [min, max] }
 * @returns {Array<Object>} - Array of n personality vectors
 */
export function generateLHS(n, d = 8, ranges = null) {
  const dimensions = PERSONALITY_DIMENSIONS.slice(0, d);
  
  // Step 1: Create stratified samples for each dimension
  const samples = [];
  for (let dim = 0; dim < d; dim++) {
    const dimSamples = [];
    for (let i = 0; i < n; i++) {
      // Each sample is in its own stratum: [(i/n), ((i+1)/n)]
      // Add random jitter within the stratum
      const lower = i / n;
      const upper = (i + 1) / n;
      dimSamples.push(lower + Math.random() * (upper - lower));
    }
    samples.push(dimSamples);
  }

  // Step 2: Randomly permute each dimension independently
  for (let dim = 0; dim < d; dim++) {
    shuffleArray(samples[dim]);
  }

  // Step 3: Assemble into personality vectors
  const vectors = [];
  for (let i = 0; i < n; i++) {
    const vector = {};
    for (let dim = 0; dim < d; dim++) {
      let value = samples[dim][i];
      
      // Apply per-dimension ranges if provided
      if (ranges && ranges[dimensions[dim]]) {
        const [min, max] = ranges[dimensions[dim]];
        value = min + value * (max - min);
      }
      
      vector[dimensions[dim]] = Math.round(value * 100) / 100;
    }
    vectors.push(vector);
  }

  return vectors;
}

/**
 * Generate LHS vectors constrained to archetype-specific ranges.
 * 
 * @param {number} count - Number of vectors to generate
 * @param {Object} archetypeRanges - Personality ranges from archetype definition
 * @returns {Array<Object>} - Constrained personality vectors
 */
export function generateConstrainedLHS(count, archetypeRanges) {
  return generateLHS(count, PERSONALITY_DIMENSIONS.length, archetypeRanges);
}

/**
 * Verify that a set of vectors has good diversity.
 * Returns a diversity score between 0 (no diversity) and 1 (maximum diversity).
 */
export function measureDiversity(vectors) {
  if (vectors.length < 2) return 1;

  const dimensions = PERSONALITY_DIMENSIONS;
  let totalDistance = 0;
  let comparisons = 0;

  for (let i = 0; i < vectors.length; i++) {
    for (let j = i + 1; j < vectors.length; j++) {
      let distance = 0;
      for (const dim of dimensions) {
        const diff = (vectors[i][dim] || 0) - (vectors[j][dim] || 0);
        distance += diff * diff;
      }
      totalDistance += Math.sqrt(distance);
      comparisons++;
    }
  }

  const avgDistance = totalDistance / comparisons;
  // Normalize: max possible distance in 8D unit cube is sqrt(8) ≈ 2.83
  const maxDistance = Math.sqrt(dimensions.length);
  
  return Math.round((avgDistance / maxDistance) * 100) / 100;
}

/**
 * Fisher-Yates shuffle
 */
function shuffleArray(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
  return array;
}
