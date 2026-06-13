import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import connectDB from "@/lib/db/connect";
import Agent from "@/lib/db/models/Agent";
import Simulation from "@/lib/db/models/Simulation";
import Project from "@/lib/db/models/Project";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";
import { NotFoundError, ValidationError } from "@/lib/utils/errors";

// POST /api/agents/custom
export const POST = withErrorHandler(
  withAuth(async (request) => {
    await connectDB();
    const { simulationId, description, scenario } = await request.json();

    if (!simulationId) return errorResponse("simulationId is required", 400);
    if (!description) return errorResponse("description is required", 400);

    const simulation = await Simulation.findById(simulationId);
    if (!simulation) throw new NotFoundError("Simulation");

    const project = await Project.findById(simulation.projectId);
    if (!project || project.userId.toString() !== request.userId) {
      throw new ValidationError("Not authorized");
    }

    const agent = await Agent.create({
      simulationId,
      persona: {
        name: "Custom Agent",
        age: 30,
        background: description,
        location: "Custom",
        occupation: "Custom scenario agent",
      },
      archetypeId: "custom",
      archetypeName: "Custom Agent",
      variantType: "custom",
      motivation: scenario || description,
      isCustom: true,
      isProductSpecific: false,
      knowledgeProfile: { knows: [], doesntKnow: [], domainExpertise: "" },
      constraints: {},
      personalityVector: {
        frugality: 0.5, techSavviness: 0.5, patience: 0.5, socialInfluence: 0.5,
        riskTolerance: 0.5, privacyConsciousness: 0.5, ethicalFlexibility: 0.5, persistence: 0.5,
      },
      generationsParticipated: [],
      findings: [],
    });

    // Add to simulation
    simulation.agentIds.push(agent._id);
    await simulation.save();

    return successResponse(agent.toJSON(), {}, 201);
  })
);
