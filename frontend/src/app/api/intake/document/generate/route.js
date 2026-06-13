import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { generateBlueprintFromDocuments } from "@/lib/services/blueprint";
import { parseDocuments } from "@/lib/services/documentParser";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/intake/document/generate — Generate blueprint from parsed documents
export const POST = withErrorHandler(
  withAuth(async (request) => {
    const { projectId } = await request.json();
    if (!projectId) return errorResponse("projectId is required", 400);

    // Parse documents if not already parsed
    const parsedDocuments = await parseDocuments(projectId, request.userId);

    // Generate blueprint
    const blueprint = await generateBlueprintFromDocuments(
      projectId,
      parsedDocuments,
      request.userId
    );

    return successResponse(blueprint, {}, 201);
  })
);
