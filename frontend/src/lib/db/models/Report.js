import mongoose from "mongoose";

const reportSchema = new mongoose.Schema(
  {
    simulationId: { type: mongoose.Schema.Types.ObjectId, ref: "Simulation", required: true, index: true },
    projectId: { type: mongoose.Schema.Types.ObjectId, ref: "Project", required: true },

    status: { type: String, enum: ["generating", "completed", "failed"], default: "generating" },

    executiveSummary: {
      overallRiskLevel: String,
      criticalCount: Number,
      highCount: Number,
      mediumCount: Number,
      lowCount: Number,
      summaryText: String,
      estimatedRevenueImpact: String,
    },

    attackSurfaceHeatmap: [{
      feature: String,
      attackCount: Number,
      maxSeverity: String,
      intensity: Number,
      topVulnerabilities: [mongoose.Schema.Types.ObjectId],
    }],

    threatClusters: [{
      theme: String,
      narrative: String,
      vulnerabilityIds: [mongoose.Schema.Types.ObjectId],
      combinedImpact: String,
    }],

    vulnerabilityCards: [{ type: mongoose.Schema.Types.ObjectId, ref: "Vulnerability" }],

    evolutionTree: {
      nodes: [{
        id: String,
        vulnerabilityId: mongoose.Schema.Types.ObjectId,
        title: String,
        generation: Number,
        severity: String,
        agentName: String,
      }],
      edges: [{
        source: String,
        target: String,
        relationship: String,
      }],
    },

    agentBehaviorCohorts: [{
      cohortName: String,
      percentage: Number,
      agentCount: Number,
      behaviorDescription: String,
      riskLevel: String,
      agentIds: [mongoose.Schema.Types.ObjectId],
    }],

    simulatedImpactTimeline: [{
      period: String,
      description: String,
      riskEscalation: String,
      keyEvents: [String],
    }],

    remediationRoadmap: {
      priority1: [{
        title: String, effort: String, impact: String,
        blocksExploits: [String], vulnerabilityIds: [mongoose.Schema.Types.ObjectId],
      }],
      priority2: [{
        title: String, effort: String, impact: String, vulnerabilityIds: [mongoose.Schema.Types.ObjectId],
      }],
      priority3: [{
        title: String, effort: String, impact: String, vulnerabilityIds: [mongoose.Schema.Types.ObjectId],
      }],
    },

    agentLogs: [{
      agentId: mongoose.Schema.Types.ObjectId,
      persona: mongoose.Schema.Types.Mixed,
      findings: [mongoose.Schema.Types.ObjectId],
      fullReasoning: [String],
    }],

    simulatedFunnel: [{
      stage: String, proceedPercent: Number, exploitPercent: Number,
      dropoffPercent: Number, description: String,
    }],

    frustrationIndicators: [{
      indicator: String, agentCount: Number, description: String,
    }],

    completedAt: Date,
  },
  { timestamps: true, toJSON: { transform: (doc, ret) => { delete ret.__v; return ret; } } }
);

const Report = mongoose.models.Report || mongoose.model("Report", reportSchema);
export default Report;
