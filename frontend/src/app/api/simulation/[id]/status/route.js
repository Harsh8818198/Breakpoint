import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { getSimulationStatus } from "@/lib/services/simulationEngine";
import { successResponse } from "@/lib/utils/apiResponse";

// GET /api/simulation/[id]/status
export const GET = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { id } = await params;
    const status = await getSimulationStatus(id, request.userId);
    return successResponse(status);
  })
);
