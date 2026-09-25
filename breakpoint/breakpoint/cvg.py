"""Causal Vulnerability Graph (CVG) -- post-simulation causal analysis layer.

After the evolutionary simulation produces findings, the CVG identifies the
shared root causes that explain clusters of related vulnerabilities. This
transforms the report from a ranked list of bugs into a causal debugger of
the product design.

Key insight: A root cause is a design decision or missing control that, if
changed, would eliminate multiple findings simultaneously.

One LLM call total -- compact input, structured JSON output.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from typing import Any

from .llm import LLMClient, extract_json
from .models import Finding
from . import prompts


@dataclass
class RootCause:
    """A shared causal explanation for one or more vulnerability findings."""
    id: str
    label: str
    category: str
    downstream_finding_ids: list = field(default_factory=list)
    fix_hint: str = ""

    @property
    def elimination_count(self):
        return len(self.downstream_finding_ids)

    def total_bss(self, findings_by_id):
        return round(sum(
            findings_by_id[fid].bss
            for fid in self.downstream_finding_ids
            if fid in findings_by_id
        ), 2)

    def to_dict(self, findings_by_id=None):
        d = asdict(self)
        if findings_by_id is not None:
            d['total_bss'] = self.total_bss(findings_by_id)
            d['elimination_count'] = self.elimination_count
        return d


@dataclass
class CVG:
    """Causal Vulnerability Graph -- full causal analysis result.

    root_causes          -- ordered by elimination impact (most findings first)
    isolated_finding_ids -- finding IDs with no shared root cause; fix independently
    minimal_fix_set      -- smallest root_cause IDs covering all CRITICAL findings
    """
    root_causes: list = field(default_factory=list)
    isolated_finding_ids: list = field(default_factory=list)
    minimal_fix_set: list = field(default_factory=list)

    def to_dict(self, findings_by_id=None):
        return {
            'root_causes': [rc.to_dict(findings_by_id) for rc in self.root_causes],
            'isolated_finding_ids': self.isolated_finding_ids,
            'minimal_fix_set': self.minimal_fix_set,
        }


def _build_findings_block(findings):
    """Compact LLM-readable list of findings for the CVG prompt."""
    lines = []
    for f in findings:
        desc = f.description[:200].rstrip()
        if len(f.description) > 200:
            desc += '...'
        cat = f.attack_category or 'unknown'
        lines.append(
            f'ID={f.id} | [{cat}] {f.title} '
            f'(BSS={f.bss}, {f.severity_band}) -- {desc}'
        )
    return '\n'.join(lines)


def _greedy_set_cover(root_causes, target_ids):
    """Greedy set cover over target finding IDs. Returns list of root_cause IDs."""
    uncovered = set(target_ids)
    selected = []
    remaining = list(root_causes)
    while uncovered and remaining:
        best = max(
            remaining,
            key=lambda rc: len(set(rc.downstream_finding_ids) & uncovered),
        )
        coverage = set(best.downstream_finding_ids) & uncovered
        if not coverage:
            break
        selected.append(best.id)
        uncovered -= coverage
        remaining.remove(best)
    return selected


def build_cvg(findings, llm):
    """Build the Causal Vulnerability Graph from simulation findings.

    Makes exactly ONE LLM call to identify root causes, then computes:
    - Root cause to downstream finding mappings (strict ID validation)
    - Total BSS per root cause
    - Isolated findings (not explained by any root cause)
    - Minimal fix set for all CRITICAL findings (greedy set cover)

    Fails gracefully: on any error returns empty CVG so report still renders.
    """
    if not findings:
        return CVG()

    findings_by_id = {f.id: f for f in findings}
    all_ids = set(findings_by_id)

    findings_block = _build_findings_block(findings)
    try:
        raw = llm.complete(
            prompts.CVG_SYSTEM,
            prompts.CVG_USER.format(findings_block=findings_block),
            task='cvg_analysis',
            max_tokens=llm.scale_tokens(1500),
        )
        data = extract_json(raw)
    except Exception as exc:
        print(f'[warn] CVG analysis failed ({exc}), skipping causal section.', file=sys.stderr)
        return CVG()

    root_causes = []
    claimed_ids = set()

    for rc_raw in data.get('root_causes', []):
        raw_ids = rc_raw.get('finding_ids', [])
        valid_ids = [fid for fid in raw_ids if fid in all_ids]
        unique_ids = [fid for fid in valid_ids if fid not in claimed_ids]
        if not unique_ids:
            continue
        claimed_ids.update(unique_ids)
        root_causes.append(RootCause(
            id=str(rc_raw.get('id', f'rc_{len(root_causes) + 1}')),
            label=str(rc_raw.get('label', 'Unknown root cause')),
            category=str(rc_raw.get('category', 'architecture')),
            downstream_finding_ids=unique_ids,
            fix_hint=str(rc_raw.get('fix_hint', '')),
        ))

    root_causes.sort(
        key=lambda rc: (rc.elimination_count, rc.total_bss(findings_by_id)),
        reverse=True,
    )

    isolated = sorted(all_ids - claimed_ids)
    critical_ids = {f.id for f in findings if f.severity_band == 'CRITICAL'}
    minimal_fix_set = _greedy_set_cover(root_causes, critical_ids)

    return CVG(
        root_causes=root_causes,
        isolated_finding_ids=isolated,
        minimal_fix_set=minimal_fix_set,
    )


def render_cvg_section(cvg, findings):
    """Render the CVG as a plain-text report section."""
    if not cvg.root_causes and not cvg.isolated_finding_ids:
        return '  (CVG analysis produced no groupable root causes)'

    findings_by_id = {f.id: f for f in findings}
    lines = []

    for i, rc in enumerate(cvg.root_causes, 1):
        downstream = [findings_by_id[fid] for fid in rc.downstream_finding_ids if fid in findings_by_id]
        tbss = rc.total_bss(findings_by_id)
        lines.append(f'')
        lines.append(f'  Root Cause #{i}: "{rc.label}"  [{rc.category}]')
        lines.append(f'    Eliminates {rc.elimination_count} finding(s)  |  Combined BSS: {tbss}')
        if downstream:
            titles = ', '.join(f.title for f in downstream)
            lines.append(f'    Findings: {titles}')
        if rc.fix_hint:
            lines.append(f'    Fix: {rc.fix_hint}')

    if cvg.minimal_fix_set:
        mfs_labels = [
            next((rc.label for rc in cvg.root_causes if rc.id == rid), rid)
            for rid in cvg.minimal_fix_set
        ]
        lines.append('')
        lines.append(f'  -- Minimal Fix Set ({len(cvg.minimal_fix_set)} root cause(s) covers all CRITICAL findings) --')
        for label in mfs_labels:
            lines.append(f'    * {label}')
    elif any(f.severity_band == 'CRITICAL' for f in findings):
        lines.append('')
        lines.append('  -- All CRITICAL findings are isolated (no shared root cause) --')
    else:
        lines.append('')
        lines.append('  -- No CRITICAL findings in this run --')

    if cvg.isolated_finding_ids:
        isolated_titles = [findings_by_id[fid].title for fid in cvg.isolated_finding_ids if fid in findings_by_id]
        lines.append('')
        lines.append('  -- Isolated Findings (no shared root cause -- fix independently) --')
        for title in isolated_titles:
            lines.append(f'    . {title}')

    return '\n'.join(lines)
