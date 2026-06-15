"""
FastAPI server wrapping the Breakpoint Python CLI engine.
Exposes a single SSE streaming endpoint that Next.js calls for simulation.

Run with:
  pip install fastapi uvicorn
  python server.py
Server starts on http://localhost:8000
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# Make the breakpoint package importable
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from breakpoint.llm import LLMClient
from breakpoint.agents import build_population
from breakpoint.evolution import simulate
from breakpoint.models import Blueprint, Flow
from breakpoint.blueprint import build_blueprint_from_codebase, scan_codebase, CODE_PATTERNS

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Breakpoint Python Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SimulationConfig(BaseModel):
    totalGenerations: int = 3
    totalAgents: int = 10
    intensity: str = "standard"
    agentComposition: dict[str, float] = {}
    customAgents: list[dict[str, Any]] = []
    focusAreas: list[str] = []


class SimulateRequest(BaseModel):
    """
    Accepts the Next.js blueprint document (from MongoDB) and simulation config.
    We convert it to the Python Blueprint dataclass for the engine.
    """
    blueprint: dict[str, Any]
    config: SimulationConfig = SimulationConfig()
    simulationId: str = ""


class ScanCodebaseRequest(BaseModel):
    path: str
    project_id: str = ""



# ---------------------------------------------------------------------------
# Blueprint converter: Next.js MongoDB format → Python dataclass
# ---------------------------------------------------------------------------

def nextjs_blueprint_to_python(data: dict) -> Blueprint:
    """
    Converts the rich Next.js Blueprint JSON (with identity, actors, resources,
    boundaries, flows, mechanicalDetails, knownUnknowns, attackSurfaceMap)
    into the flat Python Blueprint dataclass the CLI engine expects.
    """
    identity = data.get("identity", {})
    name = identity.get("name") or data.get("name", "Unknown Product")
    product_type = identity.get("type") or data.get("type", "SaaS web application")
    domain = identity.get("domain") or data.get("domain", "")
    stage = identity.get("stage") or data.get("stage", "")

    # Actors: list of dicts → list of strings
    actors_raw = data.get("actors", [])
    actors = []
    for a in actors_raw:
        if isinstance(a, dict):
            perms = ", ".join(a.get("permissions", []))
            actors.append(f"{a.get('name','?')} ({a.get('role','?')}): {perms}")
        elif isinstance(a, str):
            actors.append(a)

    # Resources: list of dicts → list of strings
    resources_raw = data.get("resources", [])
    resources = []
    for r in resources_raw:
        if isinstance(r, dict):
            resources.append(
                f"{r.get('name','?')} [{r.get('sensitivity','?')}]: {r.get('description','')}"
            )
        elif isinstance(r, str):
            resources.append(r)

    # Boundaries: list of dicts → list of strings
    boundaries_raw = data.get("boundaries", [])
    boundaries = []
    for b in boundaries_raw:
        if isinstance(b, dict):
            boundaries.append(
                f"{b.get('from','?')} → {b.get('to','?')}: {b.get('description','')}"
            )
        elif isinstance(b, str):
            boundaries.append(b)

    # Flows: list of dicts → list of Flow dataclasses
    flows_raw = data.get("flows", [])
    flows = []
    for f in flows_raw:
        if isinstance(f, dict):
            steps_raw = f.get("steps", [])
            steps = []
            for s in steps_raw:
                if isinstance(s, dict):
                    steps.append(f"{s.get('actor','?')}: {s.get('action','')}")
                elif isinstance(s, str):
                    steps.append(s)
            flows.append(Flow(name=f.get("name", ""), steps=steps))

    # Mechanical details: list of dicts → list of strings
    mech_raw = data.get("mechanicalDetails", [])
    mechanical_details = []
    for m in mech_raw:
        if isinstance(m, dict):
            status = m.get("status", "assumed")
            mechanical_details.append(
                f"[{status}] {m.get('feature','?')}: {m.get('detail','')}"
            )
        elif isinstance(m, str):
            mechanical_details.append(m)

    # Known unknowns: list of dicts → list of strings
    ku_raw = data.get("knownUnknowns", [])
    known_unknowns = []
    for k in ku_raw:
        if isinstance(k, dict):
            potential = k.get("attackPotential", "")
            known_unknowns.append(
                f"[{potential}] {k.get('question','?')} — {k.get('relevance','')}"
            )
        elif isinstance(k, str):
            known_unknowns.append(k)

    # Attack surface: list of dicts → list of strings
    asm_raw = data.get("attackSurfaceMap", [])
    attack_surface = []
    for a in asm_raw:
        if isinstance(a, dict):
            vectors = "; ".join(a.get("attackVectors", []))
            attack_surface.append(
                f"{a.get('feature','?')} [{a.get('riskLevel','?')}]: {vectors}"
            )
        elif isinstance(a, str):
            attack_surface.append(a)

    return Blueprint(
        name=name,
        type=product_type,
        domain=domain,
        stage=stage,
        actors=actors,
        resources=resources,
        boundaries=boundaries,
        flows=flows,
        mechanical_details=mechanical_details,
        known_unknowns=known_unknowns,
        attack_surface=attack_surface,
    )


# ---------------------------------------------------------------------------
# SSE streaming simulation endpoint
# ---------------------------------------------------------------------------

def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


async def _run_simulation_stream(request: SimulateRequest):
    """
    Generator that runs the Python simulation synchronously in a thread pool
    and yields SSE events as findings come in.
    """
    loop = asyncio.get_event_loop()

    try:
        # Convert blueprint
        bp = nextjs_blueprint_to_python(request.blueprint)

        yield _sse({"type": "status", "message": f"Blueprint loaded: {bp.name}"})
        yield _sse({"type": "status", "message": "Initializing LLM client..."})

        llm = LLMClient()

        yield _sse({
            "type": "status",
            "message": f"Using {llm.provider} / {llm.model}"
        })

        # Build agent population (blocking, run in thread)
        yield _sse({"type": "status", "message": "Generating agent population..."})
        agents = await loop.run_in_executor(
            None,
            lambda: build_population(
                bp, llm,
                total_agents=request.config.totalAgents,
                agent_composition=request.config.agentComposition,
                custom_agents=request.config.customAgents,
                focus_areas=request.config.focusAreas,
            )
        )
        yield _sse({"type": "agents_ready", "count": len(agents)})

        # Findings list to accumulate
        all_findings: list[dict] = []

        def on_event(kind: str, payload: Any) -> None:
            """Callback from the Python simulation loop → queued into async."""
            if kind == "status":
                asyncio.run_coroutine_threadsafe(
                    _queue.put({"type": "status", "message": payload.get("message", "")}),
                    loop,
                )
            elif kind == "generation_start":
                asyncio.run_coroutine_threadsafe(
                    _queue.put({"type": "generation_start", "generation": payload["generation"]}),
                    loop,
                )
            elif kind == "finding":
                finding_dict = payload.to_dict() if hasattr(payload, "to_dict") else {}
                asyncio.run_coroutine_threadsafe(
                    _queue.put({
                        "type": "finding",
                        "generation": finding_dict.get("generation", 0),
                        "title": finding_dict.get("title", ""),
                        "description": finding_dict.get("description", ""),
                        "discoveredBy": finding_dict.get("discovered_by", ""),
                        "attackCategory": finding_dict.get("attack_category", ""),
                        "bss": finding_dict.get("bss", 0),
                        "severityBand": finding_dict.get("severity_band", "LOW"),
                        "stepsToExploit": finding_dict.get("steps_to_exploit", []),
                        "impact": finding_dict.get("impact", ""),
                        "evolvedFrom": finding_dict.get("evolved_from", []),
                    }),
                    loop,
                )
                all_findings.append(finding_dict)
            elif kind == "generation_end":
                asyncio.run_coroutine_threadsafe(
                    _queue.put({
                        "type": "generation_end",
                        "generation": payload.get("generation", 0),
                        "kept": payload.get("kept", 0),
                        "raw": payload.get("raw", 0),
                    }),
                    loop,
                )

        # Async queue to bridge thread → async generator
        _queue: asyncio.Queue = asyncio.Queue()

        # Run the blocking simulation in a thread
        async def _run():
            await loop.run_in_executor(
                None,
                lambda: simulate(
                    bp, agents, llm,
                    generations=request.config.totalGenerations,
                    on_event=on_event,
                )
            )
            await _queue.put(None)  # sentinel

        task = asyncio.ensure_future(_run())

        # Stream events from the queue
        while True:
            event = await _queue.get()
            if event is None:
                break
            yield _sse(event)

        await task

        yield _sse({
            "type": "done",
            "totalFindings": len(all_findings),
            "simulationId": request.simulationId,
        })

    except Exception as e:
        yield _sse({"type": "error", "message": str(e)})


@app.post("/simulate")
async def simulate_endpoint(request: SimulateRequest):
    """
    SSE streaming endpoint.
    Next.js calls this with the blueprint JSON and gets a live stream of findings.
    """
    return StreamingResponse(
        _run_simulation_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/scan-codebase")
async def scan_codebase_endpoint(request: ScanCodebaseRequest):
    """
    Scans a local directory, builds a blueprint via LLM, and returns it.
    Used by the Next.js frontend's local-path codebase intake mode.
    """
    import asyncio
    loop = asyncio.get_event_loop()

    try:
        import os
        from pathlib import Path

        if not os.path.isdir(request.path):
            raise HTTPException(status_code=400, detail=f"Directory not found: {request.path}")

        # Count categories for UI feedback
        scanned_files = {cat: [] for cat in CODE_PATTERNS}
        ignore_dirs = {".git", "node_modules", ".next", "__pycache__", "venv", ".venv", "dist", "build"}
        total_files = 0
        for root, dirs, files in os.walk(request.path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix in {".png", ".jpg", ".gif", ".ico", ".pdf", ".zip", ".exe", ".dll"}:
                    continue
                total_files += 1
                lower_name = file.lower()
                for category, keywords in CODE_PATTERNS.items():
                    if any(kw in lower_name or kw in str(file_path).lower() for kw in keywords):
                        scanned_files[category].append(str(file_path))
                        break

        categories = {cat: len(files) for cat, files in scanned_files.items()}
        files_scanned = sum(categories.values())

        # Run blocking LLM blueprint build in thread
        llm = LLMClient()
        blueprint = await loop.run_in_executor(
            None,
            lambda: build_blueprint_from_codebase(request.path, llm)
        )

        return {
            "success": True,
            "blueprint": blueprint.to_dict(),
            "filesScanned": files_scanned,
            "totalFiles": total_files,
            "categories": categories,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok", "engine": "breakpoint-python"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Breakpoint Python Engine starting on http://localhost:8000")
    print("Next.js should call POST /simulate with blueprint JSON")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
