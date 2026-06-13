import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { successResponse } from "@/lib/utils/apiResponse";

export const POST = withErrorHandler(async () => {
  // JWT is stateless — client simply discards the token.
  // This endpoint exists for API completeness and future 
  // token blacklisting if needed.
  return successResponse({ message: "Logged out successfully" });
});
