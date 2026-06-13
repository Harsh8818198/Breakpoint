import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { configureSimulation } from "@/lib/services/simulationEngine";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/simulation/configure
export const POST = withErrorHandler(
  withAuth(async (request) => {
    const body = await request.json();
    if (!body.projectId) return errorResponse("projectId is required", 400);

    const simulation = await configureSimulation(
      body.projectId,
      body,
      request.userId
    );

    return successResponse(simulation, {}, 201);
  })
);
