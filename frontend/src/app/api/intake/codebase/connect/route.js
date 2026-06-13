import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { connectRepo } from "@/lib/services/codebaseAnalyzer";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/intake/codebase/connect
export const POST = withErrorHandler(
  withAuth(async (request) => {
    const { projectId, repoUrl, accessToken } = await request.json();

    if (!projectId) return errorResponse("projectId is required", 400);
    if (!repoUrl) return errorResponse("repoUrl is required", 400);
    if (!accessToken) return errorResponse("accessToken is required", 400);

    const result = await connectRepo(repoUrl, accessToken, projectId, request.userId);
    return successResponse(result);
  })
);
