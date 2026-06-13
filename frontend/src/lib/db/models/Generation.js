import mongoose from "mongoose";

const generationSchema = new mongoose.Schema(
  {
    simulationId: { type: mongoose.Schema.Types.ObjectId, ref: "Simulation", required: true, index: true },
    generationNumber: { type: Number, required: true },

    instruction: String,
    focusTheme: String,

    parentFindings: [{ type: mongoose.Schema.Types.ObjectId, ref: "Vulnerability" }],

    rawFindings: [{
      agentId: mongoose.Schema.Types.ObjectId,
      rawOutput: String,
      parsedVulnerability: mongoose.Schema.Types.Mixed,
      reasoning: String,
    }],

    deduplicatedFindings: [{ type: mongoose.Schema.Types.ObjectId, ref: "Vulnerability" }],

    fitnessScores: [{
      vulnerabilityId: mongoose.Schema.Types.ObjectId,
      noveltyScore: Number,
      severityScore: Number,
      compositeScore: Number,
    }],

    selectedForNextGen: [{ type: mongoose.Schema.Types.ObjectId, ref: "Vulnerability" }],

    stats: {
      totalRawFindings: { type: Number, default: 0 },
      afterDedup: { type: Number, default: 0 },
      llmCalls: { type: Number, default: 0 },
      duration: { type: Number, default: 0 },
    },

    status: { type: String, enum: ["pending", "running", "completed", "failed"], default: "pending" },
    completedAt: Date,
  },
  { timestamps: true, toJSON: { transform: (doc, ret) => { delete ret.__v; return ret; } } }
);

generationSchema.index({ simulationId: 1, generationNumber: 1 });

const Generation = mongoose.models.Generation || mongoose.model("Generation", generationSchema);
export default Generation;
