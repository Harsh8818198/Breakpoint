import connectDB from "@/lib/db/connect";
import Report from "@/lib/db/models/Report";
import Simulation from "@/lib/db/models/Simulation";
import Blueprint from "@/lib/db/models/Blueprint";
import Vulnerability from "@/lib/db/models/Vulnerability";
import Agent from "@/lib/db/models/Agent";
import Project from "@/lib/db/models/Project";
import { getLLMProviderWithFallback } from "@/lib/llm/factory";
import { getUserApiKey } from "@/lib/services/auth";
import {
  getExecutiveSummaryPrompt,
  getThreatClustersPrompt,
  getCohortAnalysisPrompt,
  getImpactTimelinePrompt,
  getRemediationRoadmapPrompt,
  getFunnelPrompt,
} from "@/lib/prompts/report/sections";
import { NotFoundError, ValidationError } from "@/lib/utils/errors";

/**
 * Generate the complete 9-section Breakpoint report
 */
export async function generateReport(simulationId, userId) {
  await connectDB();

  const simulation = await Simulation.findById(simulationId);
  if (!simulation) throw new NotFoundError("Simulation");

  const project = await Project.findById(simulation.projectId);
  if (!project || project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  const blueprint = await Blueprint.findById(simulation.blueprintId);
  const vulnerabilities = await Vulnerability.find({
    simulationId,
    isDuplicate: false,
  }).sort({ "bssScore.totalScore": -1 }).lean();
  const agents = await Agent.find({ simulationId }).lean();

  const apiKey = await getUserApiKey(userId, project.llmProvider);
  const llm = getLLMProviderWithFallback(project.llmProvider, apiKey);

  // Create report record
  let report = await Report.findOne({ simulationId });
  if (!report) {
    report = await Report.create({
      simulationId,
      projectId: project._id,
      status: "generating",
    });
  }

  const blueprintObj = blueprint.toJSON();

  try {
    // Generate all sections (some in parallel for speed)
    const [execSummary, threatClusters, cohorts, timeline, remediation, funnel] =
      await Promise.all([
        // Section 1: Executive Summary
        llm.chatJSON([{ role: "user", content: getExecutiveSummaryPrompt(vulnerabilities, blueprintObj) }]),
        // Section 3: Threat Clusters
        llm.chatJSON([{ role: "user", content: getThreatClustersPrompt(vulnerabilities) }]),
        // Section 6: Agent Behavior Cohorts
        llm.chatJSON([{ role: "user", content: getCohortAnalysisPrompt(agents, vulnerabilities) }]),
        // Section 7: Simulated Impact Timeline
        llm.chatJSON([{ role: "user", content: getImpactTimelinePrompt(vulnerabilities, blueprintObj) }]),
        // Section 8: Remediation Roadmap
        llm.chatJSON([{ role: "user", content: getRemediationRoadmapPrompt(vulnerabilities) }]),
        // Simulated Funnel + Frustration
        llm.chatJSON([{ role: "user", content: getFunnelPrompt(vulnerabilities, blueprintObj) }]),
      ]);

    // Section 1: Executive Summary
    const summaryData = execSummary.data;
    report.executiveSummary = {
      overallRiskLevel: summaryData.overallRiskLevel,
      criticalCount: vulnerabilities.filter((v) => v.bssScore?.severity === "critical").length,
      highCount: vulnerabilities.filter((v) => v.bssScore?.severity === "high").length,
      mediumCount: vulnerabilities.filter((v) => v.bssScore?.severity === "medium").length,
      lowCount: vulnerabilities.filter((v) => v.bssScore?.severity === "low").length,
      summaryText: summaryData.summaryText,
      estimatedRevenueImpact: summaryData.estimatedRevenueImpact,
    };

    // Section 2: Attack Surface Heatmap
    report.attackSurfaceHeatmap = generateHeatmapData(vulnerabilities);

    // Section 3: Threat Clusters
    const clusters = threatClusters.data.clusters || [];
    report.threatClusters = clusters.map((c) => ({
      theme: c.theme,
      narrative: c.narrative,
      vulnerabilityIds: vulnerabilities
        .filter((v) => c.vulnerabilityTitles?.includes(v.title))
        .map((v) => v._id),
      combinedImpact: c.combinedImpact,
    }));

    // Section 4: Vulnerability Cards (top 20 by BSS)
    report.vulnerabilityCards = vulnerabilities.slice(0, 20).map((v) => v._id);

    // Section 5: Evolution Tree
    report.evolutionTree = buildEvolutionTree(vulnerabilities, agents);

    // Section 6: Agent Behavior Cohorts
    const cohortData = cohorts.data.cohorts || [];
    report.agentBehaviorCohorts = cohortData.map((c) => ({
      cohortName: c.cohortName,
      percentage: c.percentage,
      agentCount: Math.round((c.percentage / 100) * agents.length),
      behaviorDescription: c.behaviorDescription,
      riskLevel: c.riskLevel,
      agentIds: [],
    }));

    // Section 7: Simulated Impact Timeline
    report.simulatedImpactTimeline = (timeline.data.timeline || []).map((t) => ({
      period: t.period,
      description: t.description,
      riskEscalation: t.riskEscalation,
      keyEvents: t.keyEvents || [],
    }));

    // Section 8: Remediation Roadmap
    const remData = remediation.data;
    report.remediationRoadmap = {
      priority1: (remData.priority1 || []).map((r) => ({
        title: r.title,
        effort: r.effort,
        impact: r.impact,
        blocksExploits: r.blocksExploits || [],
        vulnerabilityIds: [],
      })),
      priority2: (remData.priority2 || []).map((r) => ({
        title: r.title,
        effort: r.effort,
        impact: r.impact,
        vulnerabilityIds: [],
      })),
      priority3: (remData.priority3 || []).map((r) => ({
        title: r.title,
        effort: r.effort,
        impact: r.impact,
        vulnerabilityIds: [],
      })),
    };

    // Section 9: Full Agent Logs
    report.agentLogs = agents.map((agent) => ({
      agentId: agent._id,
      persona: agent.persona,
      findings: agent.findings || [],
      fullReasoning: vulnerabilities
        .filter((v) => v.discoveredBy?.toString() === agent._id.toString())
        .map((v) => v.agentReasoning)
        .filter(Boolean),
    }));

    // Simulated Funnel
    report.simulatedFunnel = (funnel.data.funnel || []).map((f) => ({
      stage: f.stage,
      proceedPercent: f.proceedPercent,
      exploitPercent: f.exploitPercent,
      dropoffPercent: f.dropoffPercent,
      description: f.description,
    }));

    // Frustration Indicators
    report.frustrationIndicators = (funnel.data.frustrationIndicators || []).map((f) => ({
      indicator: f.indicator,
      agentCount: f.agentCount,
      description: f.description,
    }));

    report.status = "completed";
    report.completedAt = new Date();
    await report.save();

    // Update simulation with report ID
    simulation.reportId = report._id;
    await simulation.save();

    return report.toJSON();
  } catch (error) {
    report.status = "failed";
    await report.save();
    throw error;
  }
}

/**
 * Generate heatmap data from vulnerabilities
 */
function generateHeatmapData(vulnerabilities) {
  const featureMap = {};

  for (const vuln of vulnerabilities) {
    const feature = vuln.targetFeature || "Unknown";
    if (!featureMap[feature]) {
      featureMap[feature] = {
        feature,
        attackCount: 0,
        maxSeverity: "low",
        vulnerabilities: [],
      };
    }
    featureMap[feature].attackCount++;
    featureMap[feature].vulnerabilities.push(vuln._id);

    const severityOrder = { critical: 4, high: 3, medium: 2, low: 1 };
    if (
      (severityOrder[vuln.bssScore?.severity] || 0) >
      (severityOrder[featureMap[feature].maxSeverity] || 0)
    ) {
      featureMap[feature].maxSeverity = vuln.bssScore?.severity || "low";
    }
  }

  const maxAttacks = Math.max(...Object.values(featureMap).map((f) => f.attackCount), 1);

  return Object.values(featureMap).map((f) => ({
    feature: f.feature,
    attackCount: f.attackCount,
    maxSeverity: f.maxSeverity,
    intensity: Math.round((f.attackCount / maxAttacks) * 100),
    topVulnerabilities: f.vulnerabilities.slice(0, 3),
  }));
}

/**
 * Build evolution tree from vulnerability lineage
 */
function buildEvolutionTree(vulnerabilities, agents) {
  const nodes = vulnerabilities.map((v) => ({
    id: v._id.toString(),
    vulnerabilityId: v._id,
    title: v.title,
    generation: v.generationNumber,
    severity: v.bssScore?.severity || "low",
    agentName: agents.find(
      (a) => a._id.toString() === v.discoveredBy?.toString()
    )?.persona?.name || "Unknown",
  }));

  const edges = [];
  for (const vuln of vulnerabilities) {
    if (vuln.evolvedFrom?.length) {
      for (const parentId of vuln.evolvedFrom) {
        edges.push({
          source: parentId.toString(),
          target: vuln._id.toString(),
          relationship: "evolved",
        });
      }
    }
  }

  return { nodes, edges };
}

/**
 * Get a report by simulation ID
 */
export async function getReport(simulationId, userId) {
  await connectDB();

  const report = await Report.findOne({ simulationId })
    .populate("vulnerabilityCards")
    .lean();
  if (!report) throw new NotFoundError("Report");

  const simulation = await Simulation.findById(simulationId);
  const project = await Project.findById(simulation?.projectId);
  if (!project || project.userId.toString() !== userId) {
    throw new NotFoundError("Report");
  }

  return report;
}

/**
 * Get a specific section of the report
 */
export async function getReportSection(simulationId, section, userId) {
  await connectDB();

  const report = await Report.findOne({ simulationId }).lean();
  if (!report) throw new NotFoundError("Report");

  const simulation = await Simulation.findById(simulationId);
  const project = await Project.findById(simulation?.projectId);
  if (!project || project.userId.toString() !== userId) {
    throw new NotFoundError("Report");
  }

  const sectionMap = {
    "executive-summary": "executiveSummary",
    heatmap: "attackSurfaceHeatmap",
    "threat-clusters": "threatClusters",
    "vulnerability-cards": "vulnerabilityCards",
    "evolution-tree": "evolutionTree",
    cohorts: "agentBehaviorCohorts",
    timeline: "simulatedImpactTimeline",
    remediation: "remediationRoadmap",
    "agent-logs": "agentLogs",
  };

  const field = sectionMap[section];
  if (!field) throw new NotFoundError("Report section");

  return { [field]: report[field] };
}
