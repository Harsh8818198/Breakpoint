"""The plain alternative to the evolutionary engine: ask the same model ONCE for the N most serious vulnerabilities.

This exists so the engine can be compared with the thing a founder would otherwise do (paste the code into one prompt).
Both arms are scored the same way: the baseline's claims are written to a report JSON and checked with

    python -m breakpoint.run --baseline baseline.json --codebase <path>
    python -m breakpoint.run --verify-report baseline.json --codebase <path>

so a baseline claim has to pass exactly the same code check an engine finding passes.

Two kinds of context:
  code       the repository's real source files (third-party / generated / test / doc files left out), line-numbered, as much as
             fits in `max_chars`. This is the strong baseline: the model sees everything the engine's agents could see.
  blueprint  the same 35 files x first 5,000 characters that the engine's blueprint is written from (the information the
             agents had before they were given real code).
"""

from __future__ import annotations

import os
import sys

from . import prompts
from .codeindex import CodeIndex
from .coderetrieval import check_refs, file_weight
from .llm import LLMClient, extract_json
from .models import Finding


def source_block(index: CodeIndex, max_chars: int = 300_000) -> tuple[str, dict]:
    """Numbered source of the repository's own files, most important first, until `max_chars`."""
    ranked = sorted((p for p in index.paths() if file_weight(p) >= 0.5),
                    key=lambda p: (-file_weight(p), sum(len(x) + 1 for x in index.lines(p)), p))
    parts, used, left_out = [], 0, []
    for path in ranked:
        text = index.excerpt(path, [], whole_if_chars=10 ** 9)
        if used + len(text) > max_chars:
            left_out.append(path)
            continue
        parts.append(text)
        used += len(text)
    return "\n\n".join(parts), {"files": len(parts), "chars": used, "left_out": left_out}


def build_baseline(root: str, llm: LLMClient, *, context: str = "code", n: int = 15, max_chars: int = 300_000) -> dict:
    index = CodeIndex.from_dir(root)
    if context == "blueprint":
        from .blueprint import scan_codebase
        code_block, _ = scan_codebase(root)
        meta = {"files": code_block.count("--- FILE:"), "chars": len(code_block), "left_out": []}
    elif context == "code":
        code_block, meta = source_block(index, max_chars)
    else:
        raise ValueError(f"unknown baseline context {context!r} (use 'code' or 'blueprint')")
    if not code_block.strip():
        raise ValueError("No source code could be read from the repository.")
    print(f"Baseline ({context} context): {meta['files']} files, {meta['chars']:,} characters"
          + (f", {len(meta['left_out'])} files did not fit" if meta["left_out"] else "") + f"; asking once for {n} vulnerabilities.")
    raw = llm.complete(prompts.BASELINE_SYSTEM, prompts.BASELINE_USER.format(n=n, code_block=code_block),
                       task="baseline", max_tokens=llm.scale_tokens(8000))
    items = extract_json(raw)
    if isinstance(items, dict):         # extract_json returns the inner object when the array holds exactly one
        items = [items] if items.get("title") else (items.get("findings") or items.get("vulnerabilities") or [])
    findings: list[Finding] = []
    for d in items if isinstance(items, list) else []:
        if not isinstance(d, dict) or not d.get("title"):
            continue
        steps = d.get("steps_to_exploit", [])
        findings.append(Finding(
            title=str(d["title"]).strip(), generation=1, discovered_by="single-prompt baseline",
            description=str(d.get("description", "")),
            steps_to_exploit=[str(s) for s in steps] if isinstance(steps, list) else [str(steps)],
            impact=str(d.get("impact", "")), attack_category=str(d.get("attack_category", "")),
            code_refs=check_refs(index, d.get("code_refs"))))
    if not findings:
        raise ValueError("The model returned no usable vulnerabilities.")
    return {
        "baseline": {"model": f"{llm.provider}/{llm.model}", "context": context, "requested": n,
                     "returned": len(findings), "files_shown": meta["files"], "chars_shown": meta["chars"],
                     "files_that_did_not_fit": meta["left_out"]},
        "findings": [f.to_dict() for f in findings],
    }


def write_baseline(root: str, out_path: str, *, context: str = "code", n: int = 15) -> dict:
    import json
    llm = LLMClient()
    print(f"Provider: {llm.provider} | Model: {llm.model}")
    from .blueprint import codebase_checkout
    with codebase_checkout(root) as checkout:
        data = build_baseline(checkout, llm, context=context, n=n)
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError as e:
        sys.exit(f"Cannot write {out_path!r}: {e}")
    cited = sum(1 for f in data["findings"] if f.get("code_refs"))
    print(f"[+] Saved {data['baseline']['returned']} baseline claims to {out_path} ({cited} with a verified file:line citation). "
          f"Now check them: python -m breakpoint.run --verify-report {out_path} --codebase {root}")
    return data
