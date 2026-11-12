from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from myagent import __version__, util
from myagent import facts as facts_mod
from myagent.roles import ROLES, ROLE_BY_ID
from myagent.types import Config, DocResult

log = logging.getLogger("myagent.updater")

MANIFEST_VERSION = 1


def config_digest(cfg: Config, mode: str, out: Path) -> str:
    payload = {"mode": mode, "provider": cfg.provider, "model": cfg.model, "out": out.name}
    return util.sha256_text(facts_mod.canonical_json(payload))


def load_manifest(target: Path) -> dict | None:
    p = Path(target) / ".myagent" / "manifest.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def plan_run(target: Path, out: Path, facts: dict, cfg: Config,
             mode: str) -> tuple[list[str], list[str], dict | None]:
    manifest = load_manifest(target)
    all_ids = [r.id for r in ROLES]
    if cfg.full or manifest is None:
        return all_ids, [], manifest
    if (manifest.get("manifest_version") != MANIFEST_VERSION
            or manifest.get("schema_version") != facts.get("schema_version")
            or manifest.get("config_digest") != config_digest(cfg, mode, out)):
        return all_ids, [], manifest

    old_files = {
        p: (v.get("sha256") if isinstance(v, dict) else v)
        for p, v in manifest.get("files", {}).items()
    }
    new_files = {f["path"]: f["sha256"] for f in facts["files"]}
    changed = {p for p in set(old_files) | set(new_files)
               if old_files.get(p) != new_files.get(p)}
    new_hashes = facts_mod.key_hashes(facts)
    old_hashes = manifest.get("facts_key_hashes", {})
    changed_keys = {k for k in facts_mod.FACTS_KEYS if new_hashes[k] != old_hashes.get(k)}

    affected: list[str] = []
    up_to_date: list[str] = []
    for role in ROLES:
        entry = (manifest.get("docs") or {}).get(role.filename)
        doc_path = Path(out) / role.filename
        if entry is None or not doc_path.is_file():
            affected.append(role.id)
            continue
        try:
            drifted = util.sha256_file(doc_path) != entry.get("sha256")
        except OSError:
            drifted = True
        if drifted:
            log.warning("%s was hand-edited; regenerating (docs are build artifacts)", role.filename)
            affected.append(role.id)
            continue
        if any(util.glob_match(g, p) for g in role.globs for p in changed):
            affected.append(role.id)
            continue
        if set(role.watches) & changed_keys:
            affected.append(role.id)
            continue
        if changed & set(entry.get("sources", [])):
            affected.append(role.id)
            continue
        up_to_date.append(role.id)
    return affected, up_to_date, manifest


def save_manifest(target: Path, out: Path, facts: dict, cfg: Config, mode: str,
                  results: list[DocResult], prev: dict | None) -> dict:
    prev_docs = (prev or {}).get("docs", {})
    docs = dict(prev_docs)
    now = datetime.now(timezone.utc).isoformat()
    for res in results:
        if res.status != "written":
            continue
        old = prev_docs.get(res.filename, {})
        unresolved = len([i for i in (res.verdict.issues if res.verdict else [])
                          if i.severity in ("blocker", "major")])
        docs[res.filename] = {
            "doc_version": old.get("doc_version", 0) + 1,
            "sha256": util.sha256_text(res.markdown),
            "generated_at": now,
            "mode": res.mode,
            "sources": res.sources,
            "watches": list(ROLE_BY_ID[res.role_id].watches),
            "verdict": "approved" if res.verdict and res.verdict.approved else "flagged",
            "rounds": res.rounds_used,
            "unresolved_issues": unresolved,
        }
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "tool_version": __version__,
        "schema_version": facts["schema_version"],
        "last_run": now,
        "config_digest": config_digest(cfg, mode, out),
        "facts_sha256": facts_mod.facts_sha256(facts),
        "facts_key_hashes": facts_mod.key_hashes(facts),
        "files": {f["path"]: {"sha256": f["sha256"], "bytes": f["bytes"],
                              "language": f["language"]} for f in facts["files"]},
        "docs": docs,
    }
    p = Path(target) / ".myagent" / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    return manifest