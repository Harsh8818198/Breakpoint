import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { startConversation } from "@/lib/services/conversation";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/intake/conversation/start
export const POST = withErrorHandler(
  withAuth(async (request) => {
    const { projectId } = await request.json();

    if (!projectId) {
      return errorResponse("projectId is required", 400);
    }

    const conversation = await startConversation(projectId, request.userId);

    return successResponse(conversation, {}, 201);
  })
);
