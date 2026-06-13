import connectDB from "@/lib/db/connect";
import Generation from "@/lib/db/models/Generation";
import Vulnerability from "@/lib/db/models/Vulnerability";
import Agent from "@/lib/db/models/Agent";
import { getGenerationPrompt } from "@/lib/prompts/simulation/generations";
import { deduplicateFindings, simpleDedup } from "@/lib/services/deduplication";
import { batchScoreFitness, selectForNextGeneration } from "@/lib/services/fitnessScorer";
import { estimateBSS } from "@/lib/services/bssCalculator";
import { parallelWithLimit, extractJSONFromLLM } from "@/lib/utils/helpers";
import { GENERATION_THEMES, LLM_CONCURRENCY } from "@/lib/config/constants";

/**
 * Run a single generation of the evolutionary simulation.
 */
export async function runGeneration(
  simulationId,
  genNumber,
  agents,
  parentFindings,
  blueprint,
  llm,
  onFinding = null // SSE callback
) {
  const startTime = Date.now();
  const theme = GENERATION_THEMES[genNumber] || GENERATION_THEMES[5];
  const promptFn = getGenerationPrompt(genNumber);

  // Create generation record
  const generation = await Generation.create({
    simulationId,
    generationNumber: genNumber,
    instruction: theme.description,
    focusTheme: theme.focus,
    parentFindings: parentFindings.map((f) => f._id),
    status: "running",
  });

  let llmCalls = 0;
  const rawFindings = [];

  // Run each agent through this generation
  const agentTasks = agents.map((agent) => async () => {
    try {
      const prompt = promptFn(agent, blueprint, parentFindings);
      const response = await llm.chat([{ role: "user", content: prompt }], {
        responseFormat: "json",
      });
      llmCalls++;

      const parsed = extractJSONFromLLM(response.content);
      if (parsed) {
        rawFindings.push({
          agentId: agent._id,
          rawOutput: response.content,
          parsedVulnerability: parsed,
          reasoning: parsed.reasoning || "",
        });

        // Emit live finding via SSE callback
        if (onFinding) {
          onFinding({
            type: "finding",
            generation: genNumber,
            agent: agent.persona.name,
            title: parsed.title,
            category: parsed.category,
          });
        }
      }
    } catch (error) {
      console.warn(
        `Gen ${genNumber}: Agent ${agent.persona.name} failed: ${error.message}`
      );
    }
  });

  const concurrency = LLM_CONCURRENCY[llm.getProviderName()] || 3;
  await parallelWithLimit(agentTasks, concurrency);

  // Deduplicate findings
  let deduped;
  try {
    deduped = await deduplicateFindings(
      rawFindings.map((f) => f.parsedVulnerability),
      llm
    );
  } catch {
    // Fallback to simple dedup if embedding fails
    deduped = simpleDedup(rawFindings.map((f) => f.parsedVulnerability));
  }

  // Create Vulnerability records for unique findings
  const savedVulnerabilities = [];
  for (const finding of deduped.unique) {
    const rawFinding = rawFindings.find(
      (rf) => rf.parsedVulnerability.title === finding.title
    );

    // Calculate BSS
    const bss = estimateBSS(finding);

    const vuln = await Vulnerability.create({
      simulationId,
      generationId: generation._id,
      generationNumber: genNumber,
      discoveredBy: rawFinding?.agentId,
      evolvedFrom: finding.parentFindings
        ? parentFindings
            .filter((pf) =>
              finding.parentFindings?.some((pfTitle) =>
                pf.title?.toLowerCase().includes(pfTitle?.toLowerCase()?.slice(0, 20))
              )
            )
            .map((pf) => pf._id)
        : [],
      title: finding.title,
      description: finding.description,
      stepsToExploit: finding.stepsToExploit || [],
      category: finding.category,
      targetFeature: finding.targetFeature,
      bssScore: bss,
      impact: {
        revenue: finding.estimatedImpact?.revenue || finding.businessImpact?.revenueImpact || "",
        reputation: finding.estimatedImpact?.reputation || "",
        userTrust: "",
        estimatedExploitRate: finding.estimatedImpact?.exploitRate || "",
        timeToDiscovery: finding.businessImpact?.timeToImpact || "",
        virality: finding.estimatedImpact?.virality || "medium",
      },
      suggestedFix: {
        description: finding.suggestedFix || "",
        effort: "",
        priority: bss.severity === "critical" ? 1 : bss.severity === "high" ? 2 : 3,
        blocksExploits: 1,
      },
      isDuplicate: false,
      fitnessScore: 0,
      agentReasoning: finding.reasoning || rawFinding?.reasoning || "",
      fullLlmResponse: rawFinding?.rawOutput || "",
    });

    savedVulnerabilities.push(vuln);

    // Update agent's findings
    if (rawFinding?.agentId) {
      await Agent.findByIdAndUpdate(rawFinding.agentId, {
        $push: { findings: vuln._id, generationsParticipated: genNumber },
      });
    }
  }

  // Mark duplicates
  for (const dup of deduped.duplicates) {
    await Vulnerability.create({
      simulationId,
      generationId: generation._id,
      generationNumber: genNumber,
      discoveredBy: rawFindings.find((rf) => rf.parsedVulnerability.title === dup.title)?.agentId,
      title: dup.title || "Duplicate",
      description: dup.description || "",
      stepsToExploit: dup.stepsToExploit || [],
      category: dup.category || "",
      targetFeature: dup.targetFeature || "",
      bssScore: estimateBSS(dup),
      isDuplicate: true,
      agentReasoning: dup.reasoning || "",
    });
  }

  // Score fitness for selection
  let fitnessScores = [];
  try {
    fitnessScores = await batchScoreFitness(
      savedVulnerabilities,
      parentFindings,
      llm
    );
  } catch {
    // Fallback: use BSS as fitness score
    fitnessScores = savedVulnerabilities.map((v) => ({
      vulnerabilityId: v._id,
      noveltyScore: 0.5,
      severityScore: (v.bssScore?.totalScore || 0) / 10,
      compositeScore: (v.bssScore?.totalScore || 0) / 10,
    }));
  }

  // Natural selection
  const selectedIds = selectForNextGeneration(savedVulnerabilities, fitnessScores);

  // Update generation record
  generation.rawFindings = rawFindings;
  generation.deduplicatedFindings = savedVulnerabilities.map((v) => v._id);
  generation.fitnessScores = fitnessScores;
  generation.selectedForNextGen = selectedIds;
  generation.stats = {
    totalRawFindings: rawFindings.length,
    afterDedup: savedVulnerabilities.length,
    llmCalls,
    duration: Date.now() - startTime,
  };
  generation.status = "completed";
  generation.completedAt = new Date();
  await generation.save();

  // Update vulnerability fitness scores
  for (const score of fitnessScores) {
    await Vulnerability.findByIdAndUpdate(score.vulnerabilityId, {
      fitnessScore: score.compositeScore,
    });
  }

  // Return selected findings for next generation
  const selectedFindings = savedVulnerabilities.filter((v) =>
    selectedIds.some((id) => id.toString() === v._id.toString())
  );

  return {
    generation: generation.toJSON(),
    findings: savedVulnerabilities,
    selectedForNextGen: selectedFindings,
    stats: generation.stats,
  };
}
