"""Product intake -> Blueprint (spec STEP 1).

Implements all 3 intake modes:
- Mode 1: Conversational Product Interrogation
- Mode 2: Blueprint / Document Upload (PRDs, specs, schemas)
- Mode 3: Codebase Connection (Local directory scan)
"""

from __future__ import annotations

import os
import sys
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


# Codebase file patterns (similar to Node.js scanner)
CODE_PATTERNS = {
    "routes": ["route", "controller", "api", "page"],
    "models": ["model", "schema", "db", "prisma"],
    "middleware": ["middleware", "guard"],
    "auth": ["auth", "login", "jwt", "session"],
    "config": [".env", "config", "settings"],
    "payment": ["payment", "billing", "stripe", "razorpay", "paypal", "subscription"]
}


def scan_codebase(dir_path: str) -> str:
    """Scans local directory and extracts key code file snippets for LLM analysis."""
    scanned_files = {cat: [] for cat in CODE_PATTERNS}
    ignore_dirs = {".git", "node_modules", ".next", "__pycache__", "venv", ".venv", "dist", "build", "target"}
    
    # Traverse directory
    for root, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz", ".exe", ".dll"}:
                continue
                
            lower_name = file.lower()
            for category, keywords in CODE_PATTERNS.items():
                if any(kw in lower_name or kw in str(file_path).lower() for kw in keywords):
                    scanned_files[category].append(file_path)
                    break
                    
    selected_files = []
    priorities = ["routes", "models", "auth", "middleware", "payment", "config"]
    for cat in priorities:
        for f_path in scanned_files[cat]:
            if len(selected_files) >= 30:
                break
            selected_files.append((f_path, cat))
            
    code_block_lines = []
    for f_path, cat in selected_files:
        try:
            with open(f_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(5000)
            rel_path = os.path.relpath(f_path, dir_path)
            code_block_lines.append(f"\n--- FILE: {rel_path} ({cat}) ---\n{content}")
        except Exception:
            continue
            
    return "\n".join(code_block_lines)


def build_blueprint_from_codebase(dir_path: str, llm: LLMClient) -> Blueprint:
    if not os.path.isdir(dir_path):
        raise ValueError(f"Directory path does not exist: {dir_path}")
        
    print(f"Scanning local codebase directory: {dir_path} ...")
    code_block = scan_codebase(dir_path)
    
    if not code_block:
        raise ValueError("No source code files could be scanned or read in the directory.")
        
    print(f"Extracted codebase file context. Querying LLM...")
    raw = llm.complete(
        prompts.BLUEPRINT_FROM_CODE_SYSTEM,
        prompts.BLUEPRINT_FROM_CODE_USER.format(code_block=code_block),
        task="blueprint_codebase",
        max_tokens=llm.scale_tokens(6000)
    )
    
    data = extract_json(raw)
    flows = [Flow(name=f.get("name", ""), steps=f.get("steps", []))
             for f in data.get("flows", [])]
             
    return Blueprint(
        name=data.get("name") or Path(dir_path).name,
        type=data.get("type", "SaaS web application"),
        domain=data.get("domain", ""),
        stage=data.get("stage", "Live"),
        actors=data.get("actors", []),
        resources=data.get("resources", []),
        boundaries=data.get("boundaries", []),
        flows=flows,
        mechanical_details=data.get("mechanical_details", []),
        known_unknowns=data.get("known_unknowns", []),
        attack_surface=data.get("attack_surface", []),
    )


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
