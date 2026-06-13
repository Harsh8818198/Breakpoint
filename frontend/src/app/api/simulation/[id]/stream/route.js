import { withAuth, authenticateRequest } from "@/lib/middleware/auth";
import connectDB from "@/lib/db/connect";
import Simulation from "@/lib/db/models/Simulation";
import Vulnerability from "@/lib/db/models/Vulnerability";
import Project from "@/lib/db/models/Project";

// GET /api/simulation/[id]/stream — SSE endpoint for live results
export async function GET(request, { params }) {
  const { id } = await params;

  // Authenticate
  let userId;
  try {
    userId = await authenticateRequest(request);
  } catch {
    return new Response("Unauthorized", { status: 401 });
  }

  await connectDB();

  const simulation = await Simulation.findById(id);
  if (!simulation) {
    return new Response("Simulation not found", { status: 404 });
  }

  const project = await Project.findById(simulation.projectId);
  if (!project || project.userId.toString() !== userId) {
    return new Response("Not authorized", { status: 403 });
  }

  // Set up SSE stream
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const sendEvent = (data) => {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify(data)}\n\n`)
        );
      };

      // Poll for updates
      let lastVulnCount = 0;
      let lastGeneration = 0;

      const pollInterval = setInterval(async () => {
        try {
          const sim = await Simulation.findById(id).lean();
          if (!sim) {
            clearInterval(pollInterval);
            controller.close();
            return;
          }

          // Send progress update
          sendEvent({
            type: "progress",
            status: sim.status,
            currentGeneration: sim.currentGeneration,
            progress: sim.progress,
          });

          // Send new vulnerabilities
          const vulns = await Vulnerability.find({
            simulationId: id,
            isDuplicate: false,
          })
            .sort({ createdAt: -1 })
            .limit(5)
            .lean();

          if (vulns.length > lastVulnCount) {
            for (const vuln of vulns.slice(0, vulns.length - lastVulnCount)) {
              sendEvent({
                type: "finding",
                vulnerability: {
                  title: vuln.title,
                  category: vuln.category,
                  severity: vuln.bssScore?.severity,
                  generationNumber: vuln.generationNumber,
                },
              });
            }
            lastVulnCount = vulns.length;
          }

          // Check if simulation is done
          if (
            sim.status === "completed" ||
            sim.status === "failed" ||
            sim.status === "paused"
          ) {
            sendEvent({
              type: "complete",
              status: sim.status,
              totalFindings: sim.progress.totalVulnerabilitiesFound,
            });
            clearInterval(pollInterval);
            controller.close();
          }
        } catch (error) {
          sendEvent({ type: "error", message: error.message });
        }
      }, 3000); // Poll every 3 seconds

      // Cleanup on disconnect
      request.signal.addEventListener("abort", () => {
        clearInterval(pollInterval);
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
