import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { generateBlueprintFromConversation } from "@/lib/services/blueprint";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/intake/conversation/generate — Generate blueprint from conversation
export const POST = withErrorHandler(
  withAuth(async (request) => {
    const { projectId } = await request.json();
    if (!projectId) return errorResponse("projectId is required", 400);

    const blueprint = await generateBlueprintFromConversation(
      projectId,
      request.userId
    );

    return successResponse(blueprint, {}, 201);
  })
);
