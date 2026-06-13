import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { getReportSection } from "@/lib/services/reportGenerator";
import { successResponse } from "@/lib/utils/apiResponse";

export const GET = withErrorHandler(withAuth(async (request, { params }) => {
  const { simulationId } = await params;
  const section = await getReportSection(simulationId, "evolution-tree", request.userId);
  return successResponse(section);
}));
