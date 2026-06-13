import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { getCurrentUser } from "@/lib/services/auth";
import { successResponse } from "@/lib/utils/apiResponse";

export const GET = withErrorHandler(
  withAuth(async (request) => {
    const user = await getCurrentUser(request.userId);
    return successResponse({ user });
  })
);
