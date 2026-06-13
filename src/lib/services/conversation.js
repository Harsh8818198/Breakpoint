import connectDB from "@/lib/db/connect";
import Conversation from "@/lib/db/models/Conversation";
import Project from "@/lib/db/models/Project";
import { getLLMProviderWithFallback } from "@/lib/llm/factory";
import { getUserApiKey } from "@/lib/services/auth";
import { getOpeningPrompt, SYSTEM_PROMPT } from "@/lib/prompts/intake/openingPrompt";
import { getDecompositionPrompt } from "@/lib/prompts/intake/decomposition";
import { getFollowUpPrompt } from "@/lib/prompts/intake/followUp";
import { NotFoundError, ValidationError } from "@/lib/utils/errors";
import { MAX_FOLLOWUP_ROUNDS } from "@/lib/config/constants";

/**
 * Start a new conversational product interrogation
 */
export async function startConversation(projectId, userId) {
  await connectDB();

  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  const { openingMessage } = getOpeningPrompt();

  const conversation = await Conversation.create({
    projectId,
    messages: [
      {
        role: "assistant",
        content: openingMessage,
        metadata: { type: "opening" },
      },
    ],
    status: "active",
  });

  project.conversationId = conversation._id;
  project.intakeMode = "conversation";
  project.status = "intake";
  await project.save();

  return conversation.toJSON();
}

/**
 * Process a user message and generate a targeted follow-up response
 */
export async function processMessage(conversationId, userMessage, userId) {
  await connectDB();

  const conversation = await Conversation.findById(conversationId);
  if (!conversation) throw new NotFoundError("Conversation");

  const project = await Project.findById(conversation.projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) {
    throw new ValidationError("Not authorized");
  }

  if (conversation.status === "completed") {
    throw new ValidationError(
      "Conversation is already completed. Generate a blueprint or start a new conversation."
    );
  }

  // Add user message
  conversation.messages.push({
    role: "user",
    content: userMessage,
    metadata: { type: "user_input" },
  });

  // Get LLM provider
  const apiKey = await getUserApiKey(userId, project.llmProvider);
  const llm = getLLMProviderWithFallback(project.llmProvider, apiKey);

  // Step 1: Run decomposition on accumulated conversation
  const conversationHistory = formatConversationHistory(conversation.messages);
  const decompositionPrompt = getDecompositionPrompt(conversationHistory);

  const decompositionResult = await llm.chatJSON([
    { role: "user", content: decompositionPrompt },
  ]);

  const decomp = decompositionResult.data;

  // Update decomposition with V2 fields
  conversation.decomposition = {
    entities: [
      ...(decomp.entities?.stated || []),
      ...(decomp.entities?.implied || []),
    ],
    flows: [
      ...(decomp.flows?.stated || []),
      ...(decomp.flows?.implied || []),
    ],
    boundaries: [
      ...(decomp.boundaries?.stated || []),
      ...(decomp.boundaries?.implied || []),
    ],
    gaps: decomp.gaps || [],
    // V2 additions — stored for use in follow-up prompts
    interestingImplications: decomp.interestingImplications || [],
    coverageScore: decomp.coverageScore || {},
    riskSignals: decomp.riskSignals || [],
  };

  // Step 2: Determine if we should ask more follow-ups
  const shouldContinue = shouldAskMore(conversation, decomp);

  if (shouldContinue) {
    conversation.followUpRound += 1;

    // Build full decomp object to pass to follow-up prompt
    const fullDecomp = {
      entities: decomp.entities,
      flows: decomp.flows,
      boundaries: decomp.boundaries,
      gaps: decomp.gaps || [],
      interestingImplications: decomp.interestingImplications || [],
      coverageScore: decomp.coverageScore || {},
    };

    const followUpPrompt = getFollowUpPrompt(
      fullDecomp,
      conversationHistory,
      conversation.followUpRound
    );

    const followUpResult = await llm.chat([
      { role: "system", content: SYSTEM_PROMPT },
      ...conversation.messages.map((m) => ({
        role: m.role,
        content: m.content,
      })),
      {
        role: "user",
        content: followUpPrompt,
      },
    ]);

    conversation.messages.push({
      role: "assistant",
      content: followUpResult.content,
      metadata: {
        type: "followup",
        round: conversation.followUpRound,
        theme: getRoundTheme(conversation.followUpRound),
        gapsIdentified: decomp.gaps?.slice(0, 5) || [],
        riskSignals: decomp.riskSignals?.slice(0, 3) || [],
      },
    });
  } else {
    // Conversation is complete enough — generate a summary message
    conversation.status = "completed";

    const riskCount = decomp.riskSignals?.length || 0;
    const gapCount = decomp.gaps?.length || 0;

    conversation.messages.push({
      role: "assistant",
      content: buildCompletionMessage(riskCount, gapCount),
      metadata: { type: "summary" },
    });
  }

  await conversation.save();

  return {
    conversation: conversation.toJSON(),
    decomposition: decomp,
    isComplete: conversation.status === "completed",
    followUpRound: conversation.followUpRound,
    maxRounds: MAX_FOLLOWUP_ROUNDS,
  };
}

/**
 * Determine if more follow-up questions should be asked.
 * V2: Uses coverage scores to be smarter about when we have enough.
 */
function shouldAskMore(conversation, decomposition) {
  // Max rounds reached
  if (conversation.followUpRound >= MAX_FOLLOWUP_ROUNDS) {
    return false;
  }

  const gaps = decomposition.gaps || [];
  const coverage = decomposition.coverageScore || {};

  // Always ask at least one follow-up round
  if (conversation.followUpRound === 0) {
    return true;
  }

  // If we still have significant uncovered areas, continue
  const uncoveredAreas = Object.values(coverage).filter((v) => v === 0).length;
  if (uncoveredAreas >= 3 && conversation.followUpRound < MAX_FOLLOWUP_ROUNDS) {
    return true;
  }

  // If there are still many specific gaps, continue
  if (gaps.length >= 5 && conversation.followUpRound < 2) {
    return true;
  }

  // Check minimum viable understanding
  const hasEntities = (decomposition.entities?.stated?.length || 0) >= 2;
  const hasFlows = (decomposition.flows?.stated?.length || 0) >= 1;
  const hasBoundaries = (decomposition.boundaries?.stated?.length || 0) >= 1;

  // If we don't have basics, must ask more
  if (!hasEntities || !hasFlows || !hasBoundaries) {
    return true;
  }

  // If we're at round 2+, allow completion
  if (conversation.followUpRound >= 2) {
    return false;
  }

  // Default: keep asking if significant gaps remain
  return gaps.length >= 3;
}

/**
 * Get the theme name for a given round number
 */
function getRoundTheme(round) {
  const themes = {
    1: "Authentication & Identity",
    2: "Pricing, Limits & Enforcement",
    3: "Social Dynamics & Data Ownership",
  };
  return themes[round] || "Remaining Edge Cases";
}

/**
 * Build a natural completion message with context from the analysis
 */
function buildCompletionMessage(riskCount, gapCount) {
  return `I think I have a solid picture of your product now! 🎯

Here's what I've captured: your core flows, user boundaries, the mechanics of your key features, and ${gapCount > 0 ? `${gapCount} specific edge cases` : "the key edge cases"} that I'll want the agents to probe.

${riskCount > 0 ? `I've already spotted ${riskCount} early risk signals — I'll share those in the Blueprint verification step before we start the simulation.` : ""}

Ready to generate your Product Blueprint? This will be a structured map of everything I've understood — I'll present it back to you for review before any agents are deployed.`;
}

/**
 * Format conversation messages into readable history string
 */
function formatConversationHistory(messages) {
  return messages
    .filter((m) => m.role !== "system")
    .map((m) => {
      const role = m.role === "assistant" ? "BREAKPOINT" : "USER";
      return `${role}: ${m.content}`;
    })
    .join("\n\n");
}

/**
 * Get conversation and check ownership
 */
export async function getConversation(conversationId, userId) {
  await connectDB();

  const conversation = await Conversation.findById(conversationId);
  if (!conversation) throw new NotFoundError("Conversation");

  const project = await Project.findById(conversation.projectId);
  if (!project || project.userId.toString() !== userId) {
    throw new NotFoundError("Conversation");
  }

  return conversation.toJSON();
}
