import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import connectDB from "@/lib/db/connect";
import Project from "@/lib/db/models/Project";
import User from "@/lib/db/models/User";
import { updateSettingsSchema } from "@/lib/validators/auth";
import {
  successResponse,
  validationErrorResponse,
} from "@/lib/utils/apiResponse";
import { NotFoundError, ForbiddenError } from "@/lib/utils/errors";

// PUT /api/projects/[id]/settings — Update project LLM settings
export const PUT = withErrorHandler(
  withAuth(async (request, { params }) => {
    await connectDB();
    const { id } = await params;

    const project = await Project.findById(id);
    if (!project) throw new NotFoundError("Project");
    if (project.userId.toString() !== request.userId) throw new ForbiddenError();

    const body = await request.json();

    // Update project LLM provider
    if (body.llmProvider) {
      project.llmProvider = body.llmProvider;
      await project.save();
    }

    // Update user-level API keys if provided
    if (body.openaiApiKey !== undefined || body.geminiApiKey !== undefined || body.defaultLlmProvider !== undefined) {
      const settingsResult = updateSettingsSchema.safeParse(body);
      if (!settingsResult.success) {
        return validationErrorResponse(settingsResult.error.flatten().fieldErrors);
      }

      const updateFields = {};
      if (body.defaultLlmProvider !== undefined) {
        updateFields["settings.defaultLlmProvider"] = body.defaultLlmProvider;
      }
      if (body.openaiApiKey !== undefined) {
        updateFields["settings.openaiApiKey"] = body.openaiApiKey;
      }
      if (body.geminiApiKey !== undefined) {
        updateFields["settings.geminiApiKey"] = body.geminiApiKey;
      }

      await User.findByIdAndUpdate(request.userId, { $set: updateFields });
    }

    return successResponse({
      project: project.toJSON(),
      message: "Settings updated successfully",
    });
  })
);
