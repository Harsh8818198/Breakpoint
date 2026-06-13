import mongoose from "mongoose";

const userSchema = new mongoose.Schema(
  {
    email: {
      type: String,
      required: [true, "Email is required"],
      unique: true,
      lowercase: true,
      trim: true,
      match: [/^\S+@\S+\.\S+$/, "Please enter a valid email"],
    },
    passwordHash: {
      type: String,
      required: [true, "Password is required"],
      select: false, // Don't return password hash by default
    },
    name: {
      type: String,
      required: [true, "Name is required"],
      trim: true,
      minlength: [2, "Name must be at least 2 characters"],
      maxlength: [100, "Name cannot exceed 100 characters"],
    },
    avatar: {
      type: String,
      default: null,
    },
    settings: {
      defaultLlmProvider: {
        type: String,
        enum: ["openai", "gemini"],
        default: "gemini",
      },
      openaiApiKey: {
        type: String,
        default: null,
        select: false,
      },
      geminiApiKey: {
        type: String,
        default: null,
        select: false,
      },
    },
    plan: {
      type: String,
      enum: ["free", "pro"],
      default: "free",
    },
    lastLoginAt: {
      type: Date,
      default: null,
    },
  },
  {
    timestamps: true,
    toJSON: {
      transform: function (doc, ret) {
        delete ret.passwordHash;
        delete ret.__v;
        if (ret.settings) {
          delete ret.settings.openaiApiKey;
          delete ret.settings.geminiApiKey;
        }
        return ret;
      },
    },
  }
);

// Index for efficient queries
userSchema.index({ email: 1 });

const User = mongoose.models.User || mongoose.model("User", userSchema);

export default User;
