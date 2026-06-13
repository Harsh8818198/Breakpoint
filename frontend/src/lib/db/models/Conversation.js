import mongoose from "mongoose";

const messageSchema = new mongoose.Schema(
  {
    role: {
      type: String,
      enum: ["system", "user", "assistant"],
      required: true,
    },
    content: {
      type: String,
      required: true,
    },
    metadata: {
      type: {
        type: String,
        enum: ["opening", "followup", "clarification", "summary", "user_input"],
        default: "user_input",
      },
      // V1
      gapsIdentified: [String],
      entitiesIdentified: [String],
      // V2 additions
      round: { type: Number },
      theme: { type: String },
      riskSignals: [String],
    },
    timestamp: {
      type: Date,
      default: Date.now,
    },
  },
  { _id: true }
);

const conversationSchema = new mongoose.Schema(
  {
    projectId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Project",
      required: true,
      index: true,
    },
    messages: [messageSchema],
    decomposition: {
      entities: [String],
      flows: [String],
      boundaries: [String],
      gaps: [String],
      // V2 additions
      interestingImplications: [String],
      riskSignals: [String],
      coverageScore: { type: mongoose.Schema.Types.Mixed, default: {} },
    },
    followUpRound: {
      type: Number,
      default: 0,
      max: 3,
    },
    status: {
      type: String,
      enum: ["active", "completed"],
      default: "active",
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

// Force model recompile on hot reload (Next.js dev)
delete mongoose.models.Conversation;
const Conversation = mongoose.model("Conversation", conversationSchema);

export default Conversation;
