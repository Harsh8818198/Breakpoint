"""Product intake -> Blueprint (spec STEP 1).

Implements all 3 intake modes:
- Mode 1: Conversational Product Interrogation
- Mode 2: Blueprint / Document Upload (PRDs, specs, schemas)
- Mode 3: Codebase Connection (local path OR remote GitHub URL)

For Mode 3, pass either a local directory path OR a remote GitHub URL
(e.g. https://github.com/user/repo). Remote repos are shallow-cloned
to a temp directory, scanned, then automatically cleaned up.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .llm import LLMClient, extract_json
from .models import Blueprint, Flow
from . import prompts

_REQUIRED_FIELDS = ("name", "domain", "actors", "attack_surface", "known_unknowns")


def build_blueprint(description: str, llm: LLMClient) -> Blueprint:
    raw = llm.complete(
        prompts.BLUEPRINT_SYSTEM,
        prompts.BLUEPRINT_USER.format(description=description),
        task="blueprint",
        max_tokens=llm.scale_tokens(6000),
    )
    data = extract_json(raw)

    for field in _REQUIRED_FIELDS:
        if not data.get(field):
            print(f"[warn] Blueprint field {field!r} is empty — finding quality will suffer",
                  file=sys.stderr)

    flows = [Flow(name=f.get("name", ""), steps=f.get("steps", []))
             for f in data.get("flows", [])]
    return Blueprint(
        name=data.get("name") or "Unknown product",
        type=data.get("type", ""),
        domain=data.get("domain", ""),
        stage=data.get("stage", ""),
        actors=data.get("actors", []),
        resources=data.get("resources", []),
        boundaries=data.get("boundaries", []),
        flows=flows,
        mechanical_details=data.get("mechanical_details", []),
        known_unknowns=data.get("known_unknowns", []),
        attack_surface=data.get("attack_surface", []),
    )


def build_blueprint_from_documents(doc_paths: list[str], llm: LLMClient) -> Blueprint:
    docs_block = []
    for path in doc_paths:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            filename = Path(path).name
            docs_block.append(f"--- DOCUMENT: {filename} ---\n{content[:15000]}")
        except Exception as e:
            print(f"[warn] Failed to read document {path}: {e}", file=sys.stderr)
            
    if not docs_block:
        raise ValueError("No valid document content could be read.")
        
    raw = llm.complete(
        prompts.BLUEPRINT_FROM_DOCS_SYSTEM,
        prompts.BLUEPRINT_FROM_DOCS_USER.format(docs_block="\n\n".join(docs_block)),
        task="blueprint_docs",
        max_tokens=llm.scale_tokens(6000)
    )
    
    data = extract_json(raw)
    flows = [Flow(name=f.get("name", ""), steps=f.get("steps", []))
             for f in data.get("flows", [])]
             
    return Blueprint(
        name=data.get("name") or "Unknown product",
        type=data.get("type", ""),
        domain=data.get("domain", ""),
        stage=data.get("stage", ""),
        actors=data.get("actors", []),
        resources=data.get("resources", []),
        boundaries=data.get("boundaries", []),
        flows=flows,
        mechanical_details=data.get("mechanical_details", []),
        known_unknowns=data.get("known_unknowns", []),
        attack_surface=data.get("attack_surface", []),
    )


# Codebase file patterns — surface-level security + deep structural scan
CODE_PATTERNS = {
    "routes":     ["route", "controller", "api", "page", "endpoint", "handler", "view"],
    "models":     ["model", "schema", "db", "prisma", "entity", "dao", "repository"],
    "middleware": ["middleware", "guard", "interceptor", "filter", "hook"],
    "auth":       ["auth", "login", "jwt", "session", "oauth", "token", "password"],
    "config":     [".env", "config", "settings", "constants", "env"],
    "payment":    ["payment", "billing", "stripe", "razorpay", "paypal", "subscription"],
    # --- structural / quality scan additions ---
    "logic":      ["service", "util", "helper", "manager", "processor", "engine", "worker"],
    "tests":      ["test", "spec", "__test__", "_test"],
    "deps":       ["package.json", "requirements", "gemfile", "go.mod", "pom.xml", "cargo.toml", "pyproject"],
    "infra":      ["docker", "compose", "github/workflows", ".ci", "kubernetes", "helm", "nginx", "deploy"],
}


def scan_codebase(dir_path: str) -> tuple[str, dict]:
    """Scans local directory. Returns (code_block, structural_meta).

    structural_meta contains per-category file counts and structural signals
    (missing test coverage, missing infra, etc.) used by the brain pass.
    """
    scanned_files = {cat: [] for cat in CODE_PATTERNS}
    ignore_dirs = {".git", "node_modules", ".next", "__pycache__", "venv", ".venv",
                   "dist", "build", "target", ".pytest_cache"}

    for root, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".ico",
                                     ".pdf", ".zip", ".tar", ".gz", ".exe", ".dll"}:
                continue
            lower_name = file.lower()
            fp_lower  = str(file_path).lower()
            for category, keywords in CODE_PATTERNS.items():
                if any(kw in lower_name or kw in fp_lower for kw in keywords):
                    scanned_files[category].append(file_path)
                    break

    # Security/business-critical files get priority slots
    priorities = ["routes", "models", "auth", "middleware", "payment", "config",
                  "logic", "deps", "infra"]
    selected_files: list[tuple] = []
    for cat in priorities:
        for f_path in scanned_files[cat]:
            if len(selected_files) >= 35:
                break
            selected_files.append((f_path, cat))

    code_block_lines = []
    for f_path, cat in selected_files:
        try:
            with open(f_path, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read(5000)
            rel_path = os.path.relpath(f_path, dir_path)
            code_block_lines.append(f"\n--- FILE: {rel_path} ({cat}) ---\n{content}")
        except Exception:
            continue

    # Structural metadata — counts + absence signals
    structural_meta = {
        "file_counts": {cat: len(v) for cat, v in scanned_files.items()},
        "missing_tests":  len(scanned_files["tests"]) == 0,
        "missing_infra":  len(scanned_files["infra"]) == 0,
        "missing_deps":   len(scanned_files["deps"]) == 0,
        "has_logic":      len(scanned_files["logic"]) > 0,
    }
    return "\n".join(code_block_lines), structural_meta


def _is_remote_url(path: str) -> bool:
    return path.startswith(("http://", "https://", "git@")) or path.endswith(".git")


def _clone_repo(url: str) -> str:
    """Shallow-clone a remote git repo into a temp dir. Returns the temp dir path."""
    tmp = tempfile.mkdtemp(prefix="breakpoint_scan_")
    print(f"Cloning {url} (shallow)...")
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", url, tmp],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"git clone failed:\n{result.stderr.strip()}")
    print(f"Cloned to temporary directory: {tmp}")
    return tmp


def _render_structural_signals(meta: dict) -> str:
    """Convert structural_meta dict into a plain-text block for the brain pass prompt."""
    lines = []
    counts = meta.get("file_counts", {})
    for cat, n in counts.items():
        lines.append(f"  {cat}: {n} file(s)")
    if meta.get("missing_tests"):
        lines.append("  ⚠ NO TEST FILES DETECTED")
    if meta.get("missing_infra"):
        lines.append("  ⚠ NO CI/CD OR INFRA FILES DETECTED")
    if meta.get("missing_deps"):
        lines.append("  ⚠ NO DEPENDENCY MANIFEST DETECTED")
    return "\n".join(lines)


def build_blueprint_from_codebase(dir_path: str, llm: LLMClient) -> Blueprint:
    """Mode 3 intake: local path or remote GitHub URL.

    Runs TWO LLM passes:
      1. Attack-surface blueprint (security/business-logic focus)
      2. Brain pass: deep structural/quality/arch intelligence pass
    Brain findings are injected into mechanical_details + known_unknowns
    so ALL agents see them when reasoning about exploits.
    """
    temp_dir = None
    try:
        if _is_remote_url(dir_path):
            temp_dir = _clone_repo(dir_path)
            scan_path = temp_dir
        else:
            if not os.path.isdir(dir_path):
                raise ValueError(f"Directory path does not exist: {dir_path}")
            scan_path = dir_path

        print(f"Scanning codebase: {scan_path} ...")
        code_block, structural_meta = scan_codebase(scan_path)

        if not code_block:
            raise ValueError("No source code files could be scanned or read.")

        # --- Pass 1: Security attack-surface blueprint ---
        print("Extracted codebase file context. Querying LLM [Pass 1: blueprint]...")
        raw = llm.complete(
            prompts.BLUEPRINT_FROM_CODE_SYSTEM,
            prompts.BLUEPRINT_FROM_CODE_USER.format(code_block=code_block),
            task="blueprint_codebase",
            max_tokens=llm.scale_tokens(6000)
        )
        data = extract_json(raw)
        flows = [Flow(name=f.get("name", ""), steps=f.get("steps", []))
                 for f in data.get("flows", [])]

        mechanical_details = data.get("mechanical_details", [])
        known_unknowns = data.get("known_unknowns", [])

        # --- Pass 2: Brain pass (deep structural intelligence) ---
        print("Running brain pass [Pass 2: structural intelligence]...")
        try:
            structural_signals = _render_structural_signals(structural_meta)
            brain_raw = llm.complete(
                prompts.CODE_BRAIN_SYSTEM,
                prompts.CODE_BRAIN_USER.format(
                    structural_signals=structural_signals,
                    code_block=code_block[:30000],  # cap to avoid token overflow
                ),
                task="brain_pass",
                max_tokens=llm.scale_tokens(3000),
            )
            brain = extract_json(brain_raw)
            # Flatten all brain findings into the blueprint's known_unknowns
            brain_items = []
            category_labels = {
                "architecture_risks":    "[ARCH]",
                "hidden_failure_points": "[HIDDEN-FAIL]",
                "scalability_bombs":     "[SCALABILITY]",
                "code_quality_debt":     "[CODE-QUALITY]",
                "missing_safeguards":    "[MISSING-SAFEGUARD]",
                "dependency_risks":      "[DEP-RISK]",
                "observability_gaps":    "[OBSERVABILITY]",
                "deployment_risks":      "[DEPLOY]",
            }
            for key, label in category_labels.items():
                for item in brain.get(key, []):
                    if item:
                        brain_items.append(f"{label} {item}")
            # Inject into known_unknowns so agents treat them as high-value gaps
            known_unknowns = known_unknowns + brain_items
            print(f"Brain pass complete — {len(brain_items)} structural findings injected.")
        except Exception as e:
            print(f"[warn] Brain pass failed (non-fatal): {e}", file=sys.stderr)

        return Blueprint(
            name=data.get("name") or Path(scan_path).name,
            type=data.get("type", "SaaS web application"),
            domain=data.get("domain", ""),
            stage=data.get("stage", "Live"),
            actors=data.get("actors", []),
            resources=data.get("resources", []),
            boundaries=data.get("boundaries", []),
            flows=flows,
            mechanical_details=mechanical_details,
            known_unknowns=known_unknowns,
            attack_surface=data.get("attack_surface", []),
        )
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("Cleaned up temporary clone.")


def interrogate(blueprint: Blueprint, llm: LLMClient) -> list[str]:
    """Phase 2: targeted follow-up questions for the founder.

    Wired up now so the verification loop is a small step from here, not a
    rewrite. Returns the questions; collecting answers + regenerating the
    blueprint is the interactive loop to build into the frontend.
    """
    raw = llm.complete(
        prompts.FOLLOWUP_SYSTEM,
        prompts.FOLLOWUP_USER.format(blueprint=blueprint.to_prompt_block()),
        task="followup",
        max_tokens=llm.scale_tokens(1000),
    )
    data = extract_json(raw)
    return data if isinstance(data, list) else []
