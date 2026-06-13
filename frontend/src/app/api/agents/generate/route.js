import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { generateAgentPopulation, getAgents } from "@/lib/services/agentGenerator";
import connectDB from "@/lib/db/connect";
import Simulation from "@/lib/db/models/Simulation";
import Project from "@/lib/db/models/Project";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";
import { NotFoundError, ValidationError } from "@/lib/utils/errors";

// POST /api/agents/generate
export const POST = withErrorHandler(
  withAuth(async (request) => {
    await connectDB();
    const { simulationId } = await request.json();
    if (!simulationId) return errorResponse("simulationId is required", 400);

    const simulation = await Simulation.findById(simulationId);
    if (!simulation) throw new NotFoundError("Simulation");

    const project = await Project.findById(simulation.projectId);
    if (!project || project.userId.toString() !== request.userId) {
      throw new ValidationError("Not authorized");
    }

    const result = await generateAgentPopulation(
      simulationId,
      simulation.blueprintId,
      simulation.config,
      request.userId,
      project.llmProvider
    );

    return successResponse(result, {}, 201);
  })
);
