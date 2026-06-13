import { withErrorHandler } from "@/lib/middleware/errorHandler";
import { withAuth } from "@/lib/middleware/auth";
import { getReportSection } from "@/lib/services/reportGenerator";
import { successResponse } from "@/lib/utils/apiResponse";

// Individual section endpoints
// Each follows the same pattern — extract section name from URL

async function handleSectionRequest(request, params, sectionName) {
  const { simulationId } = await params;
  const section = await getReportSection(simulationId, sectionName, request.userId);
  return successResponse(section);
}

// These are imported as dynamic routes in Next.js
// For the section-specific routes, we create a reusable pattern
export function createSectionRoute(sectionName) {
  return withErrorHandler(
    withAuth(async (request, { params }) => {
      return handleSectionRequest(request, params, sectionName);
    })
  );
}
