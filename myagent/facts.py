from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

SCHEMA_VERSION = 1

FACTS_KEYS = (
    "repo", "files", "symbols", "imports", "routes", "models", "migrations",
    "dependencies", "frameworks", "auth", "env_vars", "mcp", "integrations",
    "tests", "ci", "entrypoints", "scripts", "error_handling", "logging",
    "config_files", "docs_existing", "excerpts", "parse_errors", "stats",
    "truncation",
)

_DICT_KEYS = frozenset({
    "repo", "dependencies", "auth", "mcp", "tests", "logging", "stats", "truncation",
})


class FactsError(ValueError):
    pass


def _empty(key: str):
    if key == "repo":
        return {"root": "", "name": "", "file_count": 0, "total_bytes": 0,
                "languages": [], "primary_language": ""}
    if key == "dependencies":
        return {"manifests": [], "runtime": [], "lockfiles": []}
    if key == "auth":
        return {"patterns": [], "middleware": [], "protected_route_hints": []}
    if key == "mcp":
        return {"configs": [], "sdk_usage": []}
    if key == "tests":
        return {"frameworks": [], "config_files": [], "test_files": [],
                "coverage_config": False}
    if key == "logging":
        return {"libraries": [], "evidence": []}
    if key == "stats":
        return {"todos": [], "largest_files": []}
    if key == "truncation":
        return {"cap_hit": False, "omitted": {}}
    return []


def new_facts() -> dict:
    f = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    for k in FACTS_KEYS:
        f[k] = _empty(k)
    return f


def validate_facts(facts: dict) -> None:
    if not isinstance(facts, dict):
        raise FactsError("facts must be a dict")
    for k in FACTS_KEYS:
        if k not in facts:
            raise FactsError(f"missing facts key: {k}")
        expected = dict if k in _DICT_KEYS else list
        if not isinstance(facts[k], expected):
            raise FactsError(f"facts key {k!r} must be {expected.__name__}")


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def key_hashes(facts: dict) -> dict[str, str]:
    return {
        k: hashlib.sha256(canonical_json(facts[k]).encode("utf-8")).hexdigest()
        for k in FACTS_KEYS
    }


def facts_sha256(facts: dict) -> str:
    payload = {k: v for k, v in facts.items() if k != "generated_at"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()