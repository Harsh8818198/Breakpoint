import connectDB from "@/lib/db/connect";
import Blueprint from "@/lib/db/models/Blueprint";
import Project from "@/lib/db/models/Project";
import Conversation from "@/lib/db/models/Conversation";
import { getLLMProviderWithFallback } from "@/lib/llm/factory";
import { getUserApiKey } from "@/lib/services/auth";
import {
  getBlueprintGenerationPrompt,
  getVerificationPrompt,
  getRiskPreviewPrompt,
} from "@/lib/prompts/blueprint/generation";
import {
  NotFoundError,
  ValidationError,
  BlueprintLockedError,
} from "@/lib/utils/errors";
import { MAX_REFINEMENT_CYCLES, BLUEPRINT_STATUS } from "@/lib/config/constants";

/**
 * Generate a Product Blueprint from conversation data
 */
export async function generateBlueprintFromConversation(projectId, userId) {
  await connectDB();

  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  if (!project.conversationId) {
    throw new ValidationError("No conversation found. Start a conversation first.");
  }

  const conversation = await Conversation.findById(project.conversationId);
  if (!conversation) throw new NotFoundError("Conversation");

  // Prepare source data from conversation
  const sourceData = {
    type: "conversation",
    messages: conversation.messages.map((m) => ({
      role: m.role,
      content: m.content,
    })),
    decomposition: conversation.decomposition,
  };

  return await _generateBlueprint(project, sourceData, userId);
}

/**
 * Generate a Product Blueprint from uploaded documents
 */
export async function generateBlueprintFromDocuments(projectId, parsedDocuments, userId) {
  await connectDB();

  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  const sourceData = {
    type: "document",
    documents: parsedDocuments,
  };

  return await _generateBlueprint(project, sourceData, userId);
}

/**
 * Generate a Product Blueprint from codebase analysis
 */
export async function generateBlueprintFromCodebase(projectId, analysisResults, userId) {
  await connectDB();

  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  const sourceData = {
    type: "codebase",
    analysis: analysisResults,
  };

  return await _generateBlueprint(project, sourceData, userId);
}

/**
 * Internal: Generate blueprint from any source data
 */
async function _generateBlueprint(project, sourceData, userId) {
  const apiKey = await getUserApiKey(userId, project.llmProvider);
  const llm = getLLMProviderWithFallback(project.llmProvider, apiKey);

  const prompt = getBlueprintGenerationPrompt(sourceData);
  const result = await llm.chatJSON([{ role: "user", content: prompt }], null, { maxTokens: 8192 });

  const blueprintData = sanitizeBlueprintData(result.data);

  // Check if blueprint already exists for this project
  let blueprint = await Blueprint.findOne({ projectId: project._id });

  if (blueprint) {
    // Update existing blueprint (new version)
    blueprint.version += 1;
    Object.assign(blueprint, blueprintData);
    blueprint.status = BLUEPRINT_STATUS.DRAFT;
    blueprint.rawSourceData = _getRawSourceData(sourceData, project);
    await blueprint.save();
  } else {
    // Create new blueprint
    blueprint = await Blueprint.create({
      projectId: project._id,
      ...blueprintData,
      status: BLUEPRINT_STATUS.DRAFT,
      rawSourceData: _getRawSourceData(sourceData, project),
    });
  }

  // Update project
  project.blueprintId = blueprint._id;
  project.status = "verification";
  await project.save();

  return blueprint.toJSON();
}

/**
 * Get blueprint verification presentation
 */
export async function getVerificationPresentation(blueprintId, userId) {
  await connectDB();

  const blueprint = await Blueprint.findById(blueprintId);
  if (!blueprint) throw new NotFoundError("Blueprint");

  const project = await Project.findById(blueprint.projectId);
  if (!project || project.userId.toString() !== userId) {
    throw new NotFoundError("Blueprint");
  }

  const apiKey = await getUserApiKey(userId, project.llmProvider);
  const llm = getLLMProviderWithFallback(project.llmProvider, apiKey);

  const prompt = getVerificationPrompt(blueprint.toJSON());
  const result = await llm.chatJSON([{ role: "user", content: prompt }]);

  return {
    blueprint: blueprint.toJSON(),
    verification: result.data,
  };
}

/**
 * Refine blueprint based on user feedback
 */
export async function refineBlueprint(blueprintId, refinements, userId) {
  await connectDB();

  const blueprint = await Blueprint.findById(blueprintId);
  if (!blueprint) throw new NotFoundError("Blueprint");
  if (blueprint.status === BLUEPRINT_STATUS.LOCKED) {
    throw new BlueprintLockedError();
  }

  const project = await Project.findById(blueprint.projectId);
  if (!project || project.userId.toString() !== userId) {
    throw new NotFoundError("Blueprint");
  }

  if (blueprint.refinementCount >= MAX_REFINEMENT_CYCLES) {
    throw new ValidationError(
      `Maximum refinement cycles (${MAX_REFINEMENT_CYCLES}) reached. Please lock the blueprint to proceed.`
    );
  }

  const apiKey = await getUserApiKey(userId, project.llmProvider);
  const llm = getLLMProviderWithFallback(project.llmProvider, apiKey);

  // Generate refined blueprint
  const refinementPrompt = `You are refining a Product Blueprint based on user feedback.

CURRENT BLUEPRINT:
${JSON.stringify(blueprint.toJSON(), null, 2)}

USER FEEDBACK / CORRECTIONS:
${JSON.stringify(refinements, null, 2)}

Apply the user's corrections and generate an UPDATED complete blueprint in the same JSON format as before. Make sure to:
1. Apply all corrections the user specified
2. Update assumptions that the user confirmed or denied
3. Keep everything else unchanged unless the corrections imply changes
4. Re-evaluate the attack surface map and risks based on the corrections

Return the complete updated blueprint as JSON.`;

  const result = await llm.chatJSON([{ role: "user", content: refinementPrompt }]);

  // Apply refinements
  const updatedData = sanitizeBlueprintData(result.data);
  Object.assign(blueprint, updatedData);
  blueprint.refinementCount += 1;
  blueprint.version += 1;
  blueprint.status = BLUEPRINT_STATUS.UNDER_REVIEW;
  await blueprint.save();

  return blueprint.toJSON();
}

/**
 * Lock blueprint for simulation
 */
export async function lockBlueprint(blueprintId, userId) {
  await connectDB();

  const blueprint = await Blueprint.findById(blueprintId);
  if (!blueprint) throw new NotFoundError("Blueprint");

  const project = await Project.findById(blueprint.projectId);
  if (!project || project.userId.toString() !== userId) {
    throw new NotFoundError("Blueprint");
  }

  blueprint.status = BLUEPRINT_STATUS.LOCKED;
  await blueprint.save();

  project.status = "ready";
  await project.save();

  return blueprint.toJSON();
}

/**
 * Identify pre-simulation risks
 */
export async function identifyPreSimulationRisks(blueprintId, userId) {
  await connectDB();

  const blueprint = await Blueprint.findById(blueprintId);
  if (!blueprint) throw new NotFoundError("Blueprint");

  const project = await Project.findById(blueprint.projectId);
  if (!project || project.userId.toString() !== userId) {
    throw new NotFoundError("Blueprint");
  }

  const apiKey = await getUserApiKey(userId, project.llmProvider);
  const llm = getLLMProviderWithFallback(project.llmProvider, apiKey);

  const prompt = getRiskPreviewPrompt(blueprint.toJSON());
  const result = await llm.chatJSON([{ role: "user", content: prompt }]);

  // Sanitize risks before saving
  const sanitizedRisks = (result.data.risks || []).map(p => ({
    ...p,
    severity: (p.severity?.toLowerCase() === 'critical' ? 'critical' : 
               ['high', 'medium', 'low'].includes(p.severity?.toLowerCase()) ? p.severity.toLowerCase() : 'medium')
  }));

  // Update blueprint with pre-simulation risks
  blueprint.preSimulationRisks = sanitizedRisks;
  await blueprint.save();

  return { ...result.data, risks: sanitizedRisks };
}

/**
 * Sanitize and validate blueprint data before saving to DB
 */
function sanitizeBlueprintData(data) {
  if (!data) return data;

  const sanitized = { ...data };

  // Helper to ensure array of objects, with JSON string healing
  const ensureObjectArray = (arr, fields) => {
    let target = arr;
    
    // If the entire field is a string, try parsing it as JSON
    if (typeof target === 'string' && (target.trim().startsWith('[') || target.trim().startsWith('{'))) {
      try {
        target = JSON.parse(target.trim());
      } catch (e) {
        // Fallback or heal if necessary
      }
    }

    if (!Array.isArray(target)) return [];
    
    return target.map(item => {
      // If an item in the array is a string, it might be a malformed entry or nested JSON
      if (typeof item === 'string') {
        const trimmed = item.trim();
        if (trimmed.startsWith('{')) {
          try {
            return JSON.parse(trimmed);
          } catch (e) {}
        }
        
        // Treat as the primary field value if not JSON
        const obj = {};
        fields.forEach((f, i) => { obj[f] = i === 0 ? item : ""; });
        return obj;
      }
      return item;
    });
  };

  // Helper to ensure array of strings
  const ensureStringArray = (arr) => {
    if (!Array.isArray(arr)) return [];
    return arr.map(item => {
      if (typeof item === 'object' && item !== null) {
        // If it's an object instead of a string, try to pick a reasonable string representation
        return item.name || item.value || JSON.stringify(item);
      }
      return String(item || "");
    });
  };

  // Helper to force enum value
  const forceEnum = (val, allowed, defaultVal) => {
    if (!val) return defaultVal;
    const lowerVal = String(val).toLowerCase();
    const match = allowed.find(a => a.toLowerCase() === lowerVal);
    return match || defaultVal;
  };

  // 1. Identity Stage
  if (sanitized.identity) {
    sanitized.identity.stage = forceEnum(sanitized.identity.stage, ["pre_launch", "beta", "live", ""], "");
  }

  // 2. Actors
  sanitized.actors = ensureObjectArray(sanitized.actors, ["name", "role", "description"]);

  // 3. Resources
  sanitized.resources = ensureObjectArray(sanitized.resources, ["name", "type", "description"]).map(r => ({
    ...r,
    sensitivity: forceEnum(r.sensitivity, ["public", "private", "sensitive"], "private")
  }));

  // 4. Mechanical Details
  sanitized.mechanicalDetails = ensureObjectArray(sanitized.mechanicalDetails, ["feature", "detail"]).map(m => ({
    ...m,
    status: forceEnum(m.status, ["confirmed", "assumed", "unknown"], "assumed")
  }));

  // 5. Known Unknowns
  sanitized.knownUnknowns = ensureObjectArray(sanitized.knownUnknowns, ["question", "relevance"]).map(k => {
    // Handle 'critical' -> 'high' mapping if AI hallucinates it for potential
    let potential = k.attackPotential;
    if (potential?.toLowerCase() === 'critical') potential = 'high';
    return {
      ...k,
      attackPotential: forceEnum(potential, ["high", "medium", "low"], "medium")
    };
  });

  // 6. Attack Surface Map
  sanitized.attackSurfaceMap = ensureObjectArray(sanitized.attackSurfaceMap, ["feature"]).map(a => ({
    ...a,
    riskLevel: forceEnum(a.riskLevel, ["critical", "high", "medium", "low"], "medium"),
    attackVectors: ensureStringArray(a.attackVectors),
    relatedBoundaries: ensureStringArray(a.relatedBoundaries)
  }));

  // 7. Pre-simulation Risks
  sanitized.preSimulationRisks = ensureObjectArray(sanitized.preSimulationRisks, ["title", "description"]).map(p => ({
    ...p,
    severity: forceEnum(p.severity, ["critical", "high", "medium", "low"], "medium")
  }));

  // 8. Flows
  if (Array.isArray(sanitized.flows) || (typeof sanitized.flows === 'string' && sanitized.flows.trim().startsWith('['))) {
    sanitized.flows = ensureObjectArray(sanitized.flows, ["name"]).map(flow => {
      return {
        ...flow,
        steps: Array.isArray(flow.steps) ? flow.steps.map((step, i) => ({
          order: Number(step.order) || i + 1,
          action: String(step.action || ""),
          actor: String(step.actor || ""),
          details: String(step.details || "")
        })) : [],
        edgeCases: ensureStringArray(flow.edgeCases)
      };
    });
  }

  // 9. Actors Fix (Nested permissions)
  if (sanitized.actors) {
    sanitized.actors = sanitized.actors.map(actor => ({
      ...actor,
      permissions: ensureStringArray(actor.permissions)
    }));
  }

  return sanitized;
}

/**
 * Get blueprint by ID with ownership check
 */
export async function getBlueprint(blueprintId, userId) {
  await connectDB();

  const blueprint = await Blueprint.findById(blueprintId);
  if (!blueprint) throw new NotFoundError("Blueprint");

  const project = await Project.findById(blueprint.projectId);
  if (!project || project.userId.toString() !== userId) {
    throw new NotFoundError("Blueprint");
  }

  return blueprint.toJSON();
}

function _getRawSourceData(sourceData, project) {
  switch (sourceData.type) {
    case "conversation":
      return { conversationId: project.conversationId };
    case "document":
      return { uploadedDocuments: project.uploadedDocuments?.map((d) => d.filename) || [] };
    case "codebase":
      return { codebaseUrl: project.codebaseConfig?.repoUrl };
    default:
      return {};
  }
}
