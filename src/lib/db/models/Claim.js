import mongoose from "mongoose";

const claimSchema = new mongoose.Schema(
  {
    simulationId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Simulation",
      required: true,
      index: true,
    },
    blueprintId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "Blueprint",
      required: true,
    },

    statement: { type: String, required: true },
    category: {
      type: String,
      enum: [
        "auth",
        "rate_limit",
        "data_isolation",
        "payment",
        "business_logic",
        "ux",
        "compliance",
        "other",
      ],
      default: "other",
    },
    featureRefs: [String],
    formalizable: { type: Boolean, default: false },
    predicate: { type: String, default: null },
    severityIfFalse: {
      type: String,
      enum: ["critical", "high", "medium", "low"],
      default: "medium",
    },

    // Bayesian claim-confidence posterior: Beta(alpha, beta) on "this claim holds".
    // A failed falsification attempt nudges beta up slightly; a successful one
    // is terminal (status -> falsified).
    alpha: { type: Number, default: 1 },
    beta: { type: Number, default: 1 },
    testCount: { type: Number, default: 0 }, // n_c, used by the UCB1 allocator

    status: {
      type: String,
      enum: ["active", "falsified"],
      default: "active",
      index: true,
    },
    falsifiedBy: { type: mongoose.Schema.Types.ObjectId, ref: "Vulnerability", default: null },
    falsifiedAt: { type: Date, default: null },
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

claimSchema.index({ simulationId: 1, status: 1 });

const Claim = mongoose.models.Claim || mongoose.model("Claim", claimSchema);

export default Claim;
