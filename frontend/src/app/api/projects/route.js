import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import connectDB from "@/lib/db/connect";
import Project from "@/lib/db/models/Project";
import { createProjectSchema } from "@/lib/validators/project";
import {
  successResponse,
  validationErrorResponse,
  paginatedResponse,
} from "@/lib/utils/apiResponse";
import { getQueryParams } from "@/lib/utils/helpers";

// GET /api/projects — List user's projects
export const GET = withErrorHandler(
  withAuth(async (request) => {
    await connectDB();

    const { page = "1", limit = "10", status } = getQueryParams(request);
    const pageNum = Math.max(1, parseInt(page));
    const limitNum = Math.min(50, Math.max(1, parseInt(limit)));

    const filter = { userId: request.userId };
    if (status) filter.status = status;

    const [projects, total] = await Promise.all([
      Project.find(filter)
        .sort({ createdAt: -1 })
        .skip((pageNum - 1) * limitNum)
        .limit(limitNum)
        .lean(),
      Project.countDocuments(filter),
    ]);

    return paginatedResponse(projects, pageNum, limitNum, total);
  })
);

// POST /api/projects — Create a new project
export const POST = withErrorHandler(
  withAuth(async (request) => {
    await connectDB();

    const body = await request.json();
    const result = createProjectSchema.safeParse(body);
    if (!result.success) {
      return validationErrorResponse(result.error.flatten().fieldErrors);
    }

    const project = await Project.create({
      ...result.data,
      userId: request.userId,
    });

    return successResponse(project.toJSON(), {}, 201);
  })
);
