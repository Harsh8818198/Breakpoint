import mongoose from "mongoose";

const projectSchema = new mongoose.Schema(
  {
    userId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "User",
      required: true,
      index: true,
    },
    name: {
      type: String,
      required: [true, "Project name is required"],
      trim: true,
      maxlength: [200, "Project name too long"],
    },
    description: {
      type: String,
      default: "",
      maxlength: [2000, "Description too long"],
    },
    llmProvider: {
      type: String,
      enum: ["openai", "gemini"],
      default: "gemini",
    },
    intakeMode: {
      type: String,
      enum: ["conversation", "document", "codebase"],
      default: null,
    },
    status: {
      type: String,
      enum: ["intake", "verification", "ready", "simulating", "completed"],
      default: "intake",
    },
    blueprintId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Blueprint",
      default: null,
    },
    conversationId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Conversation",
      default: null,
    },
    simulationIds: [
      {
        type: mongoose.Schema.Types.ObjectId,
        ref: "Simulation",
      },
    ],
    // Metadata for codebase mode
    codebaseConfig: {
      repoUrl: String,
      branch: String,
      lastAnalyzedAt: Date,
    },
    // Metadata for document mode
    uploadedDocuments: [
      {
        filename: String,
        originalName: String,
        mimeType: String,
        size: Number,
        blobUrl: String,
        parsedAt: Date,
      },
    ],
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

// Compound index for user's projects
projectSchema.index({ userId: 1, createdAt: -1 });

const Project =
  mongoose.models.Project || mongoose.model("Project", projectSchema);

export default Project;
