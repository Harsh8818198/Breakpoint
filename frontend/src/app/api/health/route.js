import { NextResponse } from "next/server";

// GET /api/health — API health check and route listing
export async function GET() {
  return NextResponse.json({
    success: true,
    data: {
      name: "Breakpoint V2 API",
      version: "2.0.0",
      status: "operational",
      description: "AI-powered adversarial product testing platform",
      endpoints: {
        auth: {
          "POST /api/auth/register": "Register a new user",
          "POST /api/auth/login": "Login",
          "GET /api/auth/me": "Get current user profile",
          "POST /api/auth/logout": "Logout",
        },
        projects: {
          "GET /api/projects": "List projects",
          "POST /api/projects": "Create project",
          "GET /api/projects/:id": "Get project",
          "PUT /api/projects/:id": "Update project",
          "DELETE /api/projects/:id": "Delete project",
        },
        intake: {
          conversation: {
            "POST /api/intake/conversation/start": "Start product interrogation",
            "POST /api/intake/conversation/message": "Send message",
            "POST /api/intake/conversation/generate": "Generate blueprint",
          },
          document: {
            "POST /api/intake/document/upload": "Upload document",
            "POST /api/intake/document/parse": "Parse documents",
            "POST /api/intake/document/generate": "Generate blueprint",
          },
          codebase: {
            "POST /api/intake/codebase/connect": "Connect GitHub repo",
            "POST /api/intake/codebase/analyze": "Analyze codebase",
            "POST /api/intake/codebase/generate": "Generate blueprint",
          },
        },
        blueprint: {
          "GET /api/blueprint/:id": "Get blueprint",
          "PUT /api/blueprint/:id": "Refine blueprint",
          "POST /api/blueprint/:id/verify": "Verification presentation",
          "POST /api/blueprint/:id/lock": "Lock blueprint",
        },
        simulation: {
          "POST /api/simulation/configure": "Configure simulation",
          "POST /api/simulation/start": "Start simulation",
          "GET /api/simulation/:id/status": "Get status",
          "GET /api/simulation/:id/stream": "SSE live results",
          "POST /api/simulation/:id/stop": "Stop simulation",
        },
        report: {
          "POST /api/report/:simId/generate": "Generate report",
          "GET /api/report/:simId": "Get full report",
          "GET /api/report/:simId/executive-summary": "Executive summary",
          "GET /api/report/:simId/heatmap": "Attack surface heatmap",
          "GET /api/report/:simId/threat-clusters": "Threat clusters",
          "GET /api/report/:simId/vulnerability-cards": "Vulnerability cards",
          "GET /api/report/:simId/evolution-tree": "Evolution tree",
          "GET /api/report/:simId/cohorts": "Agent behavior cohorts",
          "GET /api/report/:simId/timeline": "Impact timeline",
          "GET /api/report/:simId/remediation": "Remediation roadmap",
          "GET /api/report/:simId/agent-logs": "Agent logs",
        },
      },
    },
  });
}
