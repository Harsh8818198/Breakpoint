import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { getVerificationPresentation, identifyPreSimulationRisks } from "@/lib/services/blueprint";
import { successResponse } from "@/lib/utils/apiResponse";

// POST /api/blueprint/[id]/verify — Get verification presentation
export const POST = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { id } = await params;
    
    const [verification, risks] = await Promise.all([
      getVerificationPresentation(id, request.userId),
      identifyPreSimulationRisks(id, request.userId),
    ]);

    return successResponse({
      ...verification,
      preSimulationRisks: risks,
    });
  })
);
