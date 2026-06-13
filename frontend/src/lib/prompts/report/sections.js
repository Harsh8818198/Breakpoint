/**
 * Report generation prompts for all 9 sections
 */

export function getExecutiveSummaryPrompt(vulnerabilities, blueprint) {
  return `Generate a one-paragraph executive summary for a product security assessment.

PRODUCT: ${blueprint.identity?.name}
TOTAL VULNERABILITIES: ${vulnerabilities.length}
CRITICAL: ${vulnerabilities.filter((v) => v.bssScore?.severity === "critical").length}
HIGH: ${vulnerabilities.filter((v) => v.bssScore?.severity === "high").length}
MEDIUM: ${vulnerabilities.filter((v) => v.bssScore?.severity === "medium").length}
LOW: ${vulnerabilities.filter((v) => v.bssScore?.severity === "low").length}

TOP VULNERABILITIES:
${vulnerabilities.slice(0, 5).map((v) => `- ${v.title} (${v.bssScore?.severity}): ${v.description}`).join("\n")}

Write a compelling executive summary in JSON:
{
  "summaryText": "One clear paragraph: what's the overall risk, what are the key threats, what should the founder do",
  "overallRiskLevel": "critical|high|medium|low",
  "estimatedRevenueImpact": "Estimated revenue impact if vulnerabilities are not fixed"
}`;
}

export function getThreatClustersPrompt(vulnerabilities) {
  return `Group these vulnerabilities into thematic clusters. Each cluster should tell a STORY — not just list findings, but explain how they're connected.

VULNERABILITIES:
${vulnerabilities.map((v) => `- "${v.title}" [Gen ${v.generationNumber}] (${v.category}): ${v.description}`).join("\n")}

Respond in JSON:
{
  "clusters": [
    {
      "theme": "Short theme name (e.g., 'Pricing Boundary Exploitation')",
      "narrative": "2-3 sentences telling the STORY of this cluster. How are these vulnerabilities connected? What pattern do they reveal?",
      "vulnerabilityTitles": ["List of vulnerability titles in this cluster"],
      "combinedImpact": "What's the combined impact of all these vulnerabilities together"
    }
  ]
}`;
}

export function getCohortAnalysisPrompt(agents, vulnerabilities) {
  return `Analyze the simulated agent population and categorize them into behavioral cohorts.

AGENTS:
${agents.slice(0, 30).map((a) => `- ${a.persona?.name} (${a.archetypeName}): ${a.motivation}`).join("\n")}

TOTAL VULNERABILITIES FOUND: ${vulnerabilities.length}

Categorize the agents into behavioral cohorts in JSON:
{
  "cohorts": [
    {
      "cohortName": "Cohort name (e.g., 'Honest Users', 'Mild Optimizers', 'Active Exploiters', 'Organized Threats')",
      "percentage": number (0-100),
      "behaviorDescription": "What this group does — are they honest? Do they exploit? Do they organize?",
      "riskLevel": "none|low|medium|high|critical"
    }
  ]
}

The cohorts should sum to 100%. Include at least 4 cohorts.`;
}

export function getImpactTimelinePrompt(vulnerabilities, blueprint) {
  return `Create a simulated 90-day impact timeline showing what would happen if this product launches with these vulnerabilities unaddressed.

PRODUCT: ${blueprint.identity?.name}
CRITICAL VULNERABILITIES: ${vulnerabilities.filter((v) => v.bssScore?.severity === "critical").map((v) => v.title).join(", ")}

Create a realistic timeline in JSON:
{
  "timeline": [
    {
      "period": "Day 1-7",
      "description": "What happens in this period",
      "riskEscalation": "How risk escalates",
      "keyEvents": ["Specific events that would occur"]
    }
  ]
}

Include 5 periods: Day 1-7, 7-14, 14-30, 30-60, 60-90.`;
}

export function getRemediationRoadmapPrompt(vulnerabilities) {
  return `Create a prioritized remediation roadmap for these vulnerabilities.

VULNERABILITIES:
${vulnerabilities.map((v) => `- "${v.title}" (${v.bssScore?.severity}, BSS: ${v.bssScore?.totalScore}): ${v.suggestedFix?.description || v.description}`).join("\n")}

Create a prioritized roadmap in JSON:
{
  "priority1": [
    {"title": "Fix title", "effort": "X days", "impact": "What this fixes", "blocksExploits": ["Which exploits this blocks"]}
  ],
  "priority2": [
    {"title": "Fix title", "effort": "X days", "impact": "What this fixes"}
  ],
  "priority3": [
    {"title": "Fix title", "effort": "X days", "impact": "What this fixes"}
  ]
}

Priority 1: Fix BEFORE launch. Priority 2: Fix within 30 days. Priority 3: Monitor and evaluate.`;
}

export function getFunnelPrompt(vulnerabilities, blueprint) {
  return `Create a simulated user funnel showing where simulated users would "drop off" or "exploit" at each stage.

PRODUCT: ${blueprint.identity?.name}
FLOWS: ${blueprint.flows?.map((f) => f.name).join(", ") || "N/A"}
VULNERABILITIES: ${vulnerabilities.map((v) => `${v.title} (targets: ${v.targetFeature})`).join(", ")}

Create a simulated funnel in JSON:
{
  "funnel": [
    {"stage": "Stage name", "proceedPercent": number, "exploitPercent": number, "dropoffPercent": number, "description": "What happens at this stage"}
  ],
  "frustrationIndicators": [
    {"indicator": "What agents found frustrating", "agentCount": number, "description": "Details"}
  ]
}`;
}
