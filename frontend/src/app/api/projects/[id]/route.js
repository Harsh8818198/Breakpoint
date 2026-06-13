import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import connectDB from "@/lib/db/connect";
import Project from "@/lib/db/models/Project";
import { updateProjectSchema } from "@/lib/validators/project";
import {
  successResponse,
  errorResponse,
  validationErrorResponse,
} from "@/lib/utils/apiResponse";
import { NotFoundError, ForbiddenError } from "@/lib/utils/errors";

// Helper to get project with ownership check
async function getProjectWithAuth(projectId, userId) {
  await connectDB();
  const project = await Project.findById(projectId);
  if (!project) throw new NotFoundError("Project");
  if (project.userId.toString() !== userId) throw new ForbiddenError();
  return project;
}

// GET /api/projects/[id]
export const GET = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { id } = await params;
    const project = await getProjectWithAuth(id, request.userId);
    return successResponse(project.toJSON());
  })
);

// PUT /api/projects/[id]
export const PUT = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { id } = await params;
    const project = await getProjectWithAuth(id, request.userId);

    const body = await request.json();
    const result = updateProjectSchema.safeParse(body);
    if (!result.success) {
      return validationErrorResponse(result.error.flatten().fieldErrors);
    }

    Object.assign(project, result.data);
    await project.save();

    return successResponse(project.toJSON());
  })
);

// DELETE /api/projects/[id]
export const DELETE = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { id } = await params;
    const project = await getProjectWithAuth(id, request.userId);

    if (project.status === "simulating") {
      return errorResponse(
        "Cannot delete a project while simulation is running",
        400
      );
    }

    await project.deleteOne();

    return successResponse({ message: "Project deleted successfully" });
  })
);
