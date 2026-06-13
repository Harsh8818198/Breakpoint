import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { lockBlueprint } from "@/lib/services/blueprint";
import { successResponse } from "@/lib/utils/apiResponse";

// POST /api/blueprint/[id]/lock — Lock blueprint for simulation
export const POST = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { id } = await params;
    const blueprint = await lockBlueprint(id, request.userId);
    return successResponse({
      blueprint,
      message: "Blueprint locked. Ready for simulation.",
    });
  })
);
