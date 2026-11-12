from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from myagent.agents import run_doc
from myagent.approver import _section_body
from myagent.roles import ROLES
from myagent.types import Config, DocResult, Role

log = logging.getLogger("myagent.orchestrator")


def _levels(selected: list[Role]) -> list[list[Role]]:
    ids = {r.id for r in selected}
    resolved: set[str] = set()
    remaining = list(selected)
    levels: list[list[Role]] = []
    while remaining:
        ready = [r for r in remaining if set(r.depends_on) & ids <= resolved]
        if not ready:
            ready = remaining
        levels.append(ready)
        resolved |= {r.id for r in ready}
        remaining = [r for r in remaining if r.id not in resolved]
    return levels


def _shared_context(results: list[DocResult]) -> str:
    by_id = {r.role_id: r for r in results if r.status == "written"}
    parts = []
    for rid, title in (("README", "What this project is"),
                       ("PRD", "Problem statement & goals"),
                       ("ARCHITECTURE", "Architecture style (inferred)")):
        res = by_id.get(rid)
        if res:
            body = _section_body(res.markdown, title)
            if body:
                parts.append(f"### {rid}: {title}\n{body.strip()[:1200]}")
    return "\n\n".join(parts)


def run(out: Path, facts: dict, cfg: Config, llm, affected_ids: list[str]) -> list[DocResult]:
    selected = [r for r in ROLES if r.id in set(affected_ids)]
    results: list[DocResult] = []
    shared = ""
    with ThreadPoolExecutor(max_workers=max(1, cfg.concurrency)) as pool:
        for level in _levels(selected):
            futures = {pool.submit(run_doc, role, facts, shared, llm, cfg): role
                       for role in level}
            for fut in as_completed(futures):
                role = futures[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    log.exception("%s: worker crashed", role.filename)
                    res = DocResult(role_id=role.id, filename=role.filename,
                                    status="failed", error=str(e))
                results.append(res)
                if res.status == "written":
                    verdict = ("APPROVED" if res.verdict and res.verdict.approved
                               else "FLAGGED")
                    log.info("%s: %s rounds=%d %s%s", role.filename, res.mode,
                             res.rounds_used, verdict, " (degraded)" if res.degraded else "")
            shared = _shared_context(results)
    return results