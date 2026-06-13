import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import {
  getBlueprint,
  refineBlueprint,
  getVerificationPresentation,
} from "@/lib/services/blueprint";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// GET /api/blueprint/[id] — Get blueprint with verification presentation
export const GET = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { id } = await params;
    const blueprint = await getBlueprint(id, request.userId);
    return successResponse(blueprint);
  })
);

// PUT /api/blueprint/[id] — Refine blueprint
export const PUT = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { id } = await params;
    const refinements = await request.json();
    const blueprint = await refineBlueprint(id, refinements, request.userId);
    return successResponse(blueprint);
  })
);
