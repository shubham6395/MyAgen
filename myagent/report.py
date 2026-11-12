from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from myagent.types import RunReport


def to_dict(report: RunReport) -> dict:
    return asdict(report)


def write_report(target: Path, report: RunReport) -> Path:
    p = Path(target) / ".myagent" / "report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(to_dict(report), indent=2, default=str),
                 encoding="utf-8", newline="\n")
    return p


def compute_exit_code(report: RunReport) -> int:
    for d in report.docs:
        if d.status == "failed" or d.degraded:
            return 4
        if d.verdict is not None and not d.verdict.approved:
            return 4
    return 0


def summarize(report: RunReport) -> str:
    lines = ["===== Summary ====="]
    for d in sorted(report.docs, key=lambda x: x.filename):
        if d.status == "failed":
            verdict = f"FAILED ({d.error})"
        elif d.verdict and d.verdict.approved:
            verdict = "APPROVED"
        else:
            n = len([i for i in (d.verdict.issues if d.verdict else [])
                     if i.severity in ("blocker", "major")])
            verdict = f"FLAGGED ({n} unresolved)"
        degraded = " DEGRADED" if d.degraded else ""
        lines.append(f"{d.filename:<18} {d.mode:<7} rounds={d.rounds_used}  {verdict}{degraded}")
    written = sum(1 for d in report.docs if d.status == "written")
    failed = sum(1 for d in report.docs if d.status == "failed")
    lines.append(f"Docs: {written} written, {len(report.up_to_date)} up-to-date, {failed} failed")
    return "\n".join(lines)