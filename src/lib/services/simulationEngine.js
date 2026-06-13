import connectDB from "@/lib/db/connect";
import Simulation from "@/lib/db/models/Simulation";
import Blueprint from "@/lib/db/models/Blueprint";
import Project from "@/lib/db/models/Project";
import Vulnerability from "@/lib/db/models/Vulnerability";
import Agent from "@/lib/db/models/Agent";
import { DEFAULT_SIMULATION_CONFIG } from "@/lib/config/defaults";
import {
  INTENSITY_PRESETS,
  SIMULATION_STATUS,
  BLUEPRINT_STATUS,
} from "@/lib/config/constants";
import {
  NotFoundError,
  ValidationError,
  SimulationError,
} from "@/lib/utils/errors";

const PYTHON_ENGINE_URL =
  process.env.PYTHON_ENGINE_URL || "http://localhost:8000";

/**
 * Configure a new simulation
 */
export async function configureSimulation(projectId, config, userId) {
  await connectDB();

  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId)
    throw new ValidationError("Not authorized");

  const blueprint = await Blueprint.findById(project.blueprintId);
  if (!blueprint || blueprint.status !== BLUEPRINT_STATUS.LOCKED) {
    throw new ValidationError(
      "Blueprint must be locked before simulation can start"
    );
  }

  const intensity = config.intensity || "standard";
  const preset = INTENSITY_PRESETS[intensity];

  const simulation = await Simulation.create({
    projectId,
    blueprintId: project.blueprintId,
    config: {
      intensity,
      totalAgents: config.totalAgents || preset.totalAgents,
      totalGenerations: config.totalGenerations || preset.totalGenerations,
      estimatedLlmCalls: preset.estimatedLlmCalls,
      estimatedDuration: preset.estimatedDuration,
      focusAreas: config.focusAreas || DEFAULT_SIMULATION_CONFIG.focusAreas,
      agentComposition:
        config.agentComposition || DEFAULT_SIMULATION_CONFIG.agentComposition,
      customAgents: config.customAgents || [],
    },
    status: SIMULATION_STATUS.CONFIGURING,
  });

  project.simulationIds.push(simulation._id);
  await project.save();

  return simulation.toJSON();
}

/**
 * Start a simulation — delegates engine work to the Python FastAPI server.
 * Results are saved to MongoDB here (Next.js side).
 */
export async function startSimulation(simulationId, userId) {
  await connectDB();

  const simulation = await Simulation.findById(simulationId);
  if (!simulation) throw new NotFoundError("Simulation");

  const project = await Project.findById(simulation.projectId);
  if (!project || project.userId.toString() !== userId)
    throw new ValidationError("Not authorized");

  if (simulation.status === SIMULATION_STATUS.RUNNING)
    throw new ValidationError("Simulation is already running");

  const blueprint = await Blueprint.findById(simulation.blueprintId);
  if (!blueprint) throw new NotFoundError("Blueprint");

  // Update status
  simulation.status = SIMULATION_STATUS.RUNNING;
  simulation.progress.startedAt = new Date();
  await simulation.save();

  project.status = "simulating";
  await project.save();

  try {
    // Check Python engine is reachable
    const healthCheck = await fetch(`${PYTHON_ENGINE_URL}/health`).catch(
      () => null
    );
    if (!healthCheck || !healthCheck.ok) {
      throw new Error(
        `Python engine is not running at ${PYTHON_ENGINE_URL}. ` +
          `Start it with: python server.py (in C:\\Users\\Sahil\\Desktop\\breakpoint\\breakpoint)`
      );
    }

    // Call the Python engine's SSE streaming endpoint
    const response = await fetch(`${PYTHON_ENGINE_URL}/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        blueprint: blueprint.toJSON(),
        config: {
          totalGenerations: simulation.config.totalGenerations,
          totalAgents: simulation.config.totalAgents,
          intensity: simulation.config.intensity,
        },
        simulationId: simulationId.toString(),
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Python engine error: ${errorText}`);
    }

    // Parse the SSE stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let agentsReady = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        let event;
        try {
          event = JSON.parse(line.slice(6));
        } catch {
          continue;
        }

        await _handleStreamEvent(event, simulation, project, agentsReady);

        if (event.type === "agents_ready") {
          agentsReady = true;
          simulation.progress.agentsGenerated = event.count || 0;
          simulation.status = SIMULATION_STATUS.RUNNING;
          await simulation.save();
        }

        if (event.type === "finding") {
          // Save finding to MongoDB
          await _saveFinding(event, simulation._id, simulationId);
          simulation.progress.totalVulnerabilitiesFound += 1;
          simulation.progress.llmCallsMade += 1;
          await simulation.save();
        }

        if (event.type === "generation_end") {
          simulation.progress.generationsCompleted = event.generation || 0;
          simulation.currentGeneration = event.generation || 0;
          await simulation.save();
        }

        if (event.type === "error") {
          throw new Error(`Python engine: ${event.message}`);
        }
      }
    }

    // Mark as completed
    simulation.status = SIMULATION_STATUS.COMPLETED;
    simulation.completedAt = new Date();
    await simulation.save();

    project.status = "completed";
    await project.save();

    return simulation.toJSON();
  } catch (error) {
    simulation.status = SIMULATION_STATUS.FAILED;
    simulation.errorLog = simulation.errorLog || [];
    simulation.errorLog.push({
      timestamp: new Date(),
      message: error.message,
      generation: simulation.currentGeneration,
    });
    await simulation.save();

    project.status = "ready";
    await project.save();

    throw new SimulationError(error.message);
  }
}

/**
 * Handle a stream event — update simulation progress fields
 */
async function _handleStreamEvent(event, simulation) {
  if (event.type === "generation_start") {
    simulation.currentGeneration = event.generation;
    await simulation.save();
  }
}

/**
 * Save a finding from the Python engine to MongoDB
 */
async function _saveFinding(event, simulationId) {
  const severityMap = {
    CRITICAL: "critical",
    HIGH: "high",
    MEDIUM: "medium",
    LOW: "low",
  };

  const severity = severityMap[event.severityBand] || "low";
  const bss = event.bss || 0;

  await Vulnerability.create({
    simulationId,
    generationNumber: event.generation || 1,
    title: event.title || "Untitled Finding",
    description: event.description || "",
    stepsToExploit: event.stepsToExploit || [],
    category: event.attackCategory || "",
    targetFeature: "",
    bssScore: {
      totalScore: bss,
      severity,
      exploitability: 0,
      impact: 0,
      spread: 0,
      fixDifficulty: 1,
    },
    impact: {
      revenue: "",
      reputation: "",
      userTrust: "",
      estimatedExploitRate: "",
      timeToDiscovery: "",
      virality: "medium",
    },
    suggestedFix: {
      description: "",
      effort: "",
      priority: severity === "critical" ? 1 : severity === "high" ? 2 : 3,
      blocksExploits: 1,
    },
    isDuplicate: false,
    fitnessScore: bss / 10,
    agentReasoning: event.discoveredBy
      ? `Discovered by ${event.discoveredBy}`
      : "",
    evolvedFrom: [],
  });
}

/**
 * Stop a running simulation
 */
export async function stopSimulation(simulationId, userId) {
  await connectDB();

  const simulation = await Simulation.findById(simulationId);
  if (!simulation) throw new NotFoundError("Simulation");

  const project = await Project.findById(simulation.projectId);
  if (!project || project.userId.toString() !== userId)
    throw new ValidationError("Not authorized");

  simulation.status = SIMULATION_STATUS.PAUSED;
  await simulation.save();

  return simulation.toJSON();
}

/**
 * Get simulation status with progress
 */
export async function getSimulationStatus(simulationId, userId) {
  await connectDB();

  const simulation = await Simulation.findById(simulationId);
  if (!simulation) throw new NotFoundError("Simulation");

  const project = await Project.findById(simulation.projectId);
  if (!project || project.userId.toString() !== userId)
    throw new NotFoundError("Simulation");

  const vulnsByGen = await Vulnerability.aggregate([
    { $match: { simulationId: simulation._id, isDuplicate: false } },
    { $group: { _id: "$generationNumber", count: { $sum: 1 } } },
    { $sort: { _id: 1 } },
  ]);

  return {
    simulation: simulation.toJSON(),
    vulnerabilitiesByGeneration: vulnsByGen,
  };
}
