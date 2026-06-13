import { cosineSimilarity } from "@/lib/utils/helpers";
import { DEDUP_CONFIG } from "@/lib/config/defaults";

/**
 * Semantic deduplication of vulnerability findings.
 * Uses embeddings to find similar findings and clusters them.
 */
export async function deduplicateFindings(findings, llm) {
  if (findings.length <= 1) return { unique: findings, duplicates: [] };

  // Generate embeddings for all findings
  const texts = findings.map(
    (f) => `${f.title}: ${f.description} [${f.category}] targeting ${f.targetFeature}`
  );

  const embeddings = await Promise.all(
    texts.map((text) => llm.embedText(text))
  );

  // Build similarity matrix and find duplicates
  const duplicates = new Set();
  const duplicateMapping = {};

  for (let i = 0; i < findings.length; i++) {
    if (duplicates.has(i)) continue;

    for (let j = i + 1; j < findings.length; j++) {
      if (duplicates.has(j)) continue;

      const similarity = cosineSimilarity(embeddings[i], embeddings[j]);

      if (similarity >= DEDUP_CONFIG.similarityThreshold) {
        // Mark the one with lower quality as duplicate
        // Quality heuristic: longer description + more steps = higher quality
        const qualityI = (findings[i].description?.length || 0) + (findings[i].stepsToExploit?.length || 0) * 50;
        const qualityJ = (findings[j].description?.length || 0) + (findings[j].stepsToExploit?.length || 0) * 50;

        if (qualityI >= qualityJ) {
          duplicates.add(j);
          duplicateMapping[j] = i;
        } else {
          duplicates.add(i);
          duplicateMapping[i] = j;
          break; // i is now a duplicate, stop comparing it
        }
      }
    }
  }

  const unique = findings.filter((_, idx) => !duplicates.has(idx));
  const dupes = findings
    .filter((_, idx) => duplicates.has(idx))
    .map((f, idx) => ({
      ...f,
      isDuplicate: true,
      duplicateOfIndex: duplicateMapping[findings.indexOf(f)],
    }));

  return { unique, duplicates: dupes };
}

/**
 * Simple text-based dedup fallback (when embeddings aren't available)
 */
export function simpleDedup(findings) {
  const seen = new Map();
  const unique = [];
  const duplicates = [];

  for (const finding of findings) {
    const key = finding.title?.toLowerCase().trim();
    if (seen.has(key)) {
      duplicates.push({ ...finding, isDuplicate: true });
    } else {
      seen.set(key, true);
      unique.push(finding);
    }
  }

  return { unique, duplicates };
}
