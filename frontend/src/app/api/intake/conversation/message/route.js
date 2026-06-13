import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { processMessage } from "@/lib/services/conversation";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/intake/conversation/message
export const POST = withErrorHandler(
  withAuth(async (request) => {
    const { conversationId, message } = await request.json();

    if (!conversationId) {
      return errorResponse("conversationId is required", 400);
    }
    if (!message || typeof message !== "string" || message.trim().length === 0) {
      return errorResponse("message is required and must be non-empty", 400);
    }

    const result = await processMessage(
      conversationId,
      message.trim(),
      request.userId
    );

    return successResponse(result);
  })
);
