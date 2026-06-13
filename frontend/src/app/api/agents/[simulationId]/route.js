import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { getAgents } from "@/lib/services/agentGenerator";
import connectDB from "@/lib/db/connect";
import Simulation from "@/lib/db/models/Simulation";
import Project from "@/lib/db/models/Project";
import { successResponse } from "@/lib/utils/apiResponse";
import { NotFoundError, ValidationError } from "@/lib/utils/errors";

// GET /api/agents/[simulationId]
export const GET = withErrorHandler(
  withAuth(async (request, { params }) => {
    await connectDB();
    const { simulationId } = await params;

    const simulation = await Simulation.findById(simulationId);
    if (!simulation) throw new NotFoundError("Simulation");

    const project = await Project.findById(simulation.projectId);
    if (!project || project.userId.toString() !== request.userId) {
      throw new ValidationError("Not authorized");
    }

    const agents = await getAgents(simulationId);
    return successResponse(agents);
  })
);
