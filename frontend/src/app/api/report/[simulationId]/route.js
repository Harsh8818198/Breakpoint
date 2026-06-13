import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { getReport } from "@/lib/services/reportGenerator";
import { successResponse } from "@/lib/utils/apiResponse";

// GET /api/report/[simulationId] — Full report
export const GET = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { simulationId } = await params;
    const report = await getReport(simulationId, request.userId);
    return successResponse(report);
  })
);
