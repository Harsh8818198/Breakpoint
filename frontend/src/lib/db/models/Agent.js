import mongoose from "mongoose";

const agentSchema = new mongoose.Schema(
  {
    simulationId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Simulation",
      required: true,
      index: true,
    },

    // 1. PERSONA (rich backstory)
    persona: {
      name: { type: String, required: true },
      age: Number,
      background: String,
      location: String,
      occupation: String,
      avatarUrl: { type: String, default: null },
    },

    // 2. ARCHETYPE & MOTIVATION
    archetypeId: { type: String, required: true },
    archetypeName: String,
    variantType: String,
    motivation: String,
    isCustom: { type: Boolean, default: false },
    isProductSpecific: { type: Boolean, default: false },

    // 3. KNOWLEDGE PROFILE
    knowledgeProfile: {
      knows: [String],
      doesntKnow: [String],
      domainExpertise: String,
    },

    // 4. BEHAVIORAL CONSTRAINTS
    constraints: {
      willingTo: [String],
      unwillingTo: [String],
      maxTimeInvestment: String,
      coordinationLevel: String,
      techSkillLevel: {
        type: String,
        enum: ["novice", "intermediate", "advanced", "expert"],
        default: "intermediate",
      },
    },

    // 5. PERSONALITY VECTOR (8 dimensions, 0-1)
    personalityVector: {
      frugality: { type: Number, min: 0, max: 1 },
      techSavviness: { type: Number, min: 0, max: 1 },
      patience: { type: Number, min: 0, max: 1 },
      socialInfluence: { type: Number, min: 0, max: 1 },
      riskTolerance: { type: Number, min: 0, max: 1 },
      privacyConsciousness: { type: Number, min: 0, max: 1 },
      ethicalFlexibility: { type: Number, min: 0, max: 1 },
      persistence: { type: Number, min: 0, max: 1 },
    },

    // Generation tracking
    findings: [{ type: mongoose.Schema.Types.ObjectId, ref: "Vulnerability" }],
    generationsParticipated: [Number],
  },
  {
    timestamps: true,
    toJSON: {
      transform: function (doc, ret) {
        delete ret.__v;
        return ret;
      },
    },
  }
);

agentSchema.index({ simulationId: 1, archetypeId: 1 });

const Agent = mongoose.models.Agent || mongoose.model("Agent", agentSchema);

export default Agent;
