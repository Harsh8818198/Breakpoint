import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { uploadDocument } from "@/lib/services/documentParser";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/intake/document/upload
export const POST = withErrorHandler(
  withAuth(async (request) => {
    const formData = await request.formData();
    const file = formData.get("file");
    const projectId = formData.get("projectId");

    if (!file) return errorResponse("No file provided", 400);
    if (!projectId) return errorResponse("projectId is required", 400);

    const result = await uploadDocument(file, projectId, request.userId);
    return successResponse(result, {}, 201);
  })
);
