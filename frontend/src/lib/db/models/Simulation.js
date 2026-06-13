import mongoose from "mongoose";

const simulationSchema = new mongoose.Schema(
  {
    projectId: { type: mongoose.Schema.Types.ObjectId, ref: "Project", required: true, index: true },
    blueprintId: { type: mongoose.Schema.Types.ObjectId, ref: "Blueprint", required: true },

    config: {
      intensity: { type: String, enum: ["light", "standard", "deep", "adversarial"], default: "standard" },
      totalAgents: { type: Number, default: 50 },
      totalGenerations: { type: Number, default: 5 },
      estimatedLlmCalls: Number,
      estimatedDuration: String,
      focusAreas: [String],
      agentComposition: { type: mongoose.Schema.Types.Mixed },
      customAgents: [{ description: String, scenario: String }],
    },

    status: {
      type: String,
      enum: ["configuring", "generating_agents", "running", "paused", "completed", "failed"],
      default: "configuring",
    },
    currentGeneration: { type: Number, default: 0 },

    progress: {
      agentsGenerated: { type: Number, default: 0 },
      generationsCompleted: { type: Number, default: 0 },
      totalVulnerabilitiesFound: { type: Number, default: 0 },
      deduplicated: { type: Number, default: 0 },
      llmCallsMade: { type: Number, default: 0 },
      startedAt: Date,
      estimatedCompletion: Date,
    },

    generationIds: [{ type: mongoose.Schema.Types.ObjectId, ref: "Generation" }],
    agentIds: [{ type: mongoose.Schema.Types.ObjectId, ref: "Agent" }],
    reportId: { type: mongoose.Schema.Types.ObjectId, ref: "Report", default: null },

    errorLog: [{ timestamp: Date, message: String, generation: Number }],
    completedAt: Date,
  },
  { timestamps: true, toJSON: { transform: (doc, ret) => { delete ret.__v; return ret; } } }
);

const Simulation = mongoose.models.Simulation || mongoose.model("Simulation", simulationSchema);
export default Simulation;
