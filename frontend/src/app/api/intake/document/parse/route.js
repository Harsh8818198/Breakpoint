import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { parseDocuments } from "@/lib/services/documentParser";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/intake/document/parse
export const POST = withErrorHandler(
  withAuth(async (request) => {
    const { projectId } = await request.json();
    if (!projectId) return errorResponse("projectId is required", 400);

    const results = await parseDocuments(projectId, request.userId);
    return successResponse(results);
  })
);
