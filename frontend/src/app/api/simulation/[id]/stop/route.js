import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { stopSimulation } from "@/lib/services/simulationEngine";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/simulation/[id]/stop
export const POST = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { id } = await params;
    const simulation = await stopSimulation(id, request.userId);
    return successResponse({
      simulation,
      message: "Simulation will stop after current generation completes.",
    });
  })
);
