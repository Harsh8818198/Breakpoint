import mongoose from "mongoose";

const blueprintSchema = new mongoose.Schema(
  {
    projectId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Project",
      required: true,
      index: true,
    },
    version: { type: Number, default: 1 },
    status: {
      type: String,
      enum: ["draft", "under_review", "locked"],
      default: "draft",
    },
    refinementCount: { type: Number, default: 0, max: 3 },

    // PRODUCT IDENTITY
    identity: {
      name: { type: String, default: "" },
      type: { type: String, default: "" },
      domain: { type: String, default: "" },
      stage: {
        type: String,
        enum: ["pre_launch", "beta", "live", ""],
        default: "",
      },
    },

    // ACTORS
    actors: [
      {
        name: String,
        role: String,
        description: String,
        permissions: [String],
      },
    ],

    // RESOURCES
    resources: [
      {
        name: String,
        type: { type: String },
        description: String,
        ownership: String,
        sensitivity: {
          type: String,
          enum: ["public", "private", "sensitive"],
          default: "private",
        },
      },
    ],

    // BOUNDARIES
    boundaries: [
      {
        from: String,
        to: String,
        trigger: String,
        description: String,
      },
    ],

    // FLOWS
    flows: [
      {
        name: String,
        steps: [
          {
            order: Number,
            action: String,
            actor: String,
            details: String,
          },
        ],
        edgeCases: [String],
      },
    ],

    // MECHANICAL DETAILS
    mechanicalDetails: [
      {
        feature: String,
        detail: String,
        status: {
          type: String,
          enum: ["confirmed", "assumed", "unknown"],
          default: "assumed",
        },
      },
    ],

    // KNOWN UNKNOWNS
    knownUnknowns: [
      {
        question: String,
        relevance: String,
        attackPotential: {
          type: String,
          enum: ["high", "medium", "low"],
          default: "medium",
        },
      },
    ],

    // ATTACK SURFACE MAP
    attackSurfaceMap: [
      {
        feature: String,
        riskLevel: {
          type: String,
          enum: ["critical", "high", "medium", "low"],
        },
        attackVectors: [String],
        relatedBoundaries: [String],
      },
    ],

    // PRE-SIMULATION RISKS
    preSimulationRisks: [
      {
        title: String,
        description: String,
        severity: {
          type: String,
          enum: ["critical", "high", "medium", "low"],
        },
      },
    ],

    // ASSUMPTIONS
    assumptions: [
      {
        statement: String,
        userVerified: { type: Boolean, default: false },
      },
    ],

    // RAW SOURCE DATA
    rawSourceData: {
      conversationId: mongoose.Schema.Types.ObjectId,
      uploadedDocuments: [String],
      codebaseUrl: String,
    },
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

const Blueprint = mongoose.models.Blueprint || mongoose.model("Blueprint", blueprintSchema);

export default Blueprint;
