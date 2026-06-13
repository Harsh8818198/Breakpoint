import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { analyzeCodebase } from "@/lib/services/codebaseAnalyzer";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/intake/codebase/analyze
export const POST = withErrorHandler(
  withAuth(async (request) => {
    const { projectId, accessToken } = await request.json();

    if (!projectId) return errorResponse("projectId is required", 400);
    if (!accessToken) return errorResponse("accessToken is required", 400);

    const result = await analyzeCodebase(projectId, accessToken, request.userId);
    return successResponse(result);
  })
);
