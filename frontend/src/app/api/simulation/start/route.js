import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { startSimulation } from "@/lib/services/simulationEngine";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/simulation/start
export const POST = withErrorHandler(
  withAuth(async (request) => {
    const { simulationId } = await request.json();
    if (!simulationId) return errorResponse("simulationId is required", 400);

    // Start simulation (this is a long-running operation)
    // In production, this would be a background job
    // For now, we start it and return immediately
    const simulation = startSimulation(simulationId, request.userId);

    // Don't await — let it run in the background
    simulation.catch((error) => {
      console.error(`Simulation ${simulationId} failed:`, error.message);
    });

    return successResponse({
      message: "Simulation started. Use the status endpoint to monitor progress.",
      simulationId,
    });
  })
);
