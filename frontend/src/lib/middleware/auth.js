import connectDB from "@/lib/db/connect";
import User from "@/lib/db/models/User";
import { AuthError } from "@/lib/utils/errors";
import { errorResponse } from "@/lib/utils/apiResponse";

/**
 * Bypasses JWT login check by returning a default Developer user ID.
 * Automatically creates the user if the database is empty.
 */
export async function authenticateRequest(request) {
  await connectDB();
  
  // Find or create default developer user
  let user = await User.findOne({ email: "dev@breakpoint.local" });
  if (!user) {
    user = await User.findOne(); // Fallback to any existing user
  }
  if (!user) {
    user = await User.create({
      email: "dev@breakpoint.local",
      name: "Developer",
      passwordHash: "dummy-password-not-used",
      settings: {
        defaultLlmProvider: "gemini",
        geminiApiKey: process.env.GEMINI_API_KEY || "",
      }
    });
  }
  
  return user._id.toString();
}

/**
 * HOF: Wraps a handler to require authentication.
 * Injects userId into the handler's context.
 */
export function withAuth(handler) {
  return async function (request, context) {
    try {
      const userId = await authenticateRequest(request);
      // Attach userId to request for downstream use
      request.userId = userId;
      return await handler(request, context);
    } catch (error) {
      if (error instanceof AuthError) {
        return errorResponse(error.message, 401);
      }
      throw error;
    }
  };
}
