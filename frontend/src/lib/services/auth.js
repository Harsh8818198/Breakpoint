import bcrypt from "bcryptjs";
import { SignJWT, jwtVerify } from "jose";
import connectDB from "@/lib/db/connect";
import User from "@/lib/db/models/User";
import { AuthError, ConflictError, NotFoundError } from "@/lib/utils/errors";

const JWT_SECRET = new TextEncoder().encode(process.env.JWT_SECRET);
const JWT_EXPIRY = process.env.JWT_EXPIRY || "7d";

/**
 * Register a new user
 */
export async function registerUser({ email, password, name }) {
  await connectDB();

  // Check if user exists
  const existing = await User.findOne({ email: email.toLowerCase() });
  if (existing) {
    throw new ConflictError("An account with this email already exists");
  }

  // Hash password
  const salt = await bcrypt.genSalt(12);
  const passwordHash = await bcrypt.hash(password, salt);

  // Create user
  const user = await User.create({
    email: email.toLowerCase(),
    passwordHash,
    name,
  });

  // Generate JWT
  const token = await generateToken(user._id.toString());

  return {
    user: user.toJSON(),
    token,
  };
}

/**
 * Login user
 */
export async function loginUser({ email, password }) {
  await connectDB();

  // Find user with password hash
  const user = await User.findOne({ email: email.toLowerCase() }).select(
    "+passwordHash"
  );
  if (!user) {
    throw new AuthError("Invalid email or password");
  }

  // Verify password
  const isValid = await bcrypt.compare(password, user.passwordHash);
  if (!isValid) {
    throw new AuthError("Invalid email or password");
  }

  // Update last login
  user.lastLoginAt = new Date();
  await user.save();

  // Generate JWT
  const token = await generateToken(user._id.toString());

  return {
    user: user.toJSON(),
    token,
  };
}

/**
 * Get current user from token
 */
export async function getCurrentUser(userId) {
  await connectDB();

  const user = await User.findById(userId);
  if (!user) {
    throw new NotFoundError("User");
  }

  return user.toJSON();
}

/**
 * Update user settings (API keys, default provider)
 */
export async function updateUserSettings(userId, settings) {
  await connectDB();

  const updateFields = {};
  if (settings.defaultLlmProvider !== undefined) {
    updateFields["settings.defaultLlmProvider"] = settings.defaultLlmProvider;
  }
  if (settings.openaiApiKey !== undefined) {
    updateFields["settings.openaiApiKey"] = settings.openaiApiKey;
  }
  if (settings.geminiApiKey !== undefined) {
    updateFields["settings.geminiApiKey"] = settings.geminiApiKey;
  }

  const user = await User.findByIdAndUpdate(
    userId,
    { $set: updateFields },
    { new: true }
  );

  if (!user) {
    throw new NotFoundError("User");
  }

  return user.toJSON();
}

/**
 * Get user's API key for a specific provider
 */
export async function getUserApiKey(userId, provider) {
  await connectDB();

  const keyField =
    provider === "openai"
      ? "settings.openaiApiKey"
      : "settings.geminiApiKey";

  const user = await User.findById(userId).select(`+${keyField}`);
  if (!user) {
    throw new NotFoundError("User");
  }

  const apiKey =
    provider === "openai"
      ? user.settings?.openaiApiKey
      : user.settings?.geminiApiKey;

  // Fall back to environment variable
  if (!apiKey) {
    const envKey =
      provider === "openai"
        ? process.env.OPENAI_API_KEY
        : process.env.GEMINI_API_KEY;
    return envKey || null;
  }

  return apiKey;
}

/**
 * Generate JWT token
 */
async function generateToken(userId) {
  return new SignJWT({ userId })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(JWT_EXPIRY)
    .sign(JWT_SECRET);
}

/**
 * Verify and decode JWT token
 */
export async function verifyToken(token) {
  try {
    const { payload } = await jwtVerify(token, JWT_SECRET);
    return payload;
  } catch (error) {
    throw new AuthError("Invalid or expired token");
  }
}
