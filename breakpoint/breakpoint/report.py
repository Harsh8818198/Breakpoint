"""Report assembly (spec STEP 5).

v0 produces the text backbone of the spec's 9-section report: executive summary,
ranked vulnerability cards with BSS, an attack-surface tally, and the evolution
tree (the demo showpiece) as nested text. The heatmap, cohort %s, and impact
timeline are richer-rendering sections for the frontend phase.
"""

from __future__ import annotations

from collections import Counter
from .models import Blueprint, Finding


def evolution_tree(findings: list[Finding]) -> dict:
    """Build parent->child lineage keyed by finding title."""
    by_title = {f.title: f for f in findings}
    children: dict[str, list[str]] = {f.title: [] for f in findings}
    roots: list[str] = []
    for f in findings:
        parents = [p for p in f.evolved_from if p in by_title]
        if parents:
            for p in parents:
                children[p].append(f.title)
        else:
            roots.append(f.title)
    return {"roots": roots, "children": children}


def _render_tree(findings: list[Finding]) -> str:
    tree = evolution_tree(findings)
    by_title = {f.title: f for f in findings}
    out: list[str] = []
    seen: set[str] = set()

    def walk(title: str, depth: int) -> None:
        if title in seen:
            out.append("  " * depth + f"- {title} (already shown above)")
            return
        seen.add(title)
        f = by_title.get(title)
        gen = f.generation if f else "?"
        out.append("  " * depth + f"- [G{gen}] {title}")
        for child in tree["children"].get(title, []):
            walk(child, depth + 1)

    for root in tree["roots"]:
        walk(root, 0)
    return "\n".join(out) if out else "(no lineage captured)"


def render_report(blueprint: Blueprint, findings: list[Finding]) -> str:
    ranked = sorted(findings, key=lambda f: f.bss, reverse=True)
    crit = [f for f in ranked if f.severity_band == "CRITICAL"]
    gens = Counter(f.generation for f in findings)

    L: list[str] = []
    L.append("=" * 70)
    L.append(f"BREAKPOINT REPORT  -  {blueprint.name}")
    L.append("=" * 70)

    # Section 1: executive summary
    gen_span = f"across {max(gens)} generations" if gens else "no generations"
    L.append("\n## EXECUTIVE SUMMARY")
    L.append(f"{len(findings)} distinct vulnerabilities {gen_span}; {len(crit)} critical.")
    if ranked:
        top = ranked[0]
        L.append(f"Top risk: {top.title} (BSS {top.bss}, {top.severity_band}).")

    # Section 2: findings per generation
    L.append("\n## FINDINGS BY GENERATION")
    for g in sorted(gens):
        items = [f for f in findings if f.generation == g]
        avg = round(sum(f.bss for f in items) / len(items), 2)
        L.append(f"  Gen {g}: {len(items)} findings  (avg BSS {avg})")

    # Section 3: vulnerability cards (ranked by BSS)
    L.append("\n## VULNERABILITY CARDS (ranked by severity)")
    for i, f in enumerate(ranked, 1):
        assumed = "  [ASSUMED - verify manually]" if f.confidence < 0.5 else ""
        cat = f"  [{f.attack_category}]" if f.attack_category else ""
        L.append(f"\n[{i}] {f.title}   <{f.severity_band}  BSS {f.bss}>  [{f.fix_priority}]{cat}{assumed}")
        L.append(f"    Found by: {f.discovered_by}  |  Generation: {f.generation}"
                 + (f"  |  confidence {f.confidence:.0%}" if f.confidence < 1.0 else ""))
        if f.evolved_from:
            L.append(f"    Evolved from: {', '.join(f.evolved_from)}")
        L.append(f"    {f.description}")
        if f.steps_to_exploit:
            L.append("    Steps: " + " | ".join(f.steps_to_exploit))
        L.append(f"    Impact: {f.impact}")
        L.append(f"    Scores -> exploit {f.exploitability} / impact "
                 f"{f.impact_score} / spread {f.spread} / fixdiff {f.fix_difficulty}")

    # Section 4: attack category breakdown
    L.append("\n## ATTACK SURFACE COVERAGE")
    cats = Counter(f.attack_category for f in findings if f.attack_category)
    if cats:
        for cat, count in cats.most_common():
            avg_conf = sum(f.confidence for f in findings if f.attack_category == cat) / count
            flag = "  ← all assumed, verify" if avg_conf < 0.5 else ""
            L.append(f"  {cat:<16} {count:>2} finding(s)  avg confidence {avg_conf:.0%}{flag}")
    else:
        L.append("  (no categories recorded)")

    # Section 5: evolution tree
    L.append("\n## EVOLUTION TREE (the showpiece)")
    L.append(_render_tree(findings))

    L.append("\n" + "=" * 70)
    return "\n".join(L)
