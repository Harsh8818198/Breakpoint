import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { generateReport } from "@/lib/services/reportGenerator";
import { successResponse, errorResponse } from "@/lib/utils/apiResponse";

// POST /api/report/[simulationId]/generate
export const POST = withErrorHandler(
  withAuth(async (request, { params }) => {
    const { simulationId } = await params;
    const report = await generateReport(simulationId, request.userId);
    return successResponse(report, {}, 201);
  })
);
