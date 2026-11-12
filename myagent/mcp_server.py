from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from myagent import __version__, config, report
from myagent.analyzer import analyze_repo
from myagent.cli import run_pipeline

log = logging.getLogger("myagent.mcp")

PROTOCOL_VERSION = "2024-11-05"

_TARGET_SCHEMA = {
    "type": "object",
    "properties": {"target": {"type": "string", "description": "Absolute path to the codebase"}},
    "required": ["target"],
}

TOOLS = [
    {
        "name": "document_codebase",
        "description": ("Generate or incrementally update the 16-document suite (PRD, DESIGN, "
                        "ARCHITECTURE, DATABASE, API, AGENTS, README, BLUEPRINT, and guides) "
                        "for a codebase. Runs worker agents plus an approver. Long runs are "
                        "normal in LLM mode; use only/offline for quick interactive runs."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "out": {"type": "string", "description": "Output dir (default <target>/docs)"},
                "only": {"type": "array", "items": {"type": "string"},
                         "description": "Restrict to these docs, e.g. [\"API\",\"PRD\"]"},
                "full": {"type": "boolean", "description": "Force regeneration of all docs"},
                "offline": {"type": "boolean", "description": "Deterministic mode, no LLM"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "analyze_codebase",
        "description": "Analyze a codebase and return a facts summary (languages, routes, models, dependencies). Writes nothing.",
        "inputSchema": _TARGET_SCHEMA,
    },
    {
        "name": "get_docs_status",
        "description": "Return the last generation report and per-document verdicts for a codebase. No regeneration.",
        "inputSchema": _TARGET_SCHEMA,
    },
]


def _text_result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _call_tool(params: dict) -> dict:
    name = params.get("name")
    args = params.get("arguments") or {}
    try:
        target = Path(args["target"]).resolve()
        if not target.is_dir():
            return _text_result(f"error: not a directory: {target}", is_error=True)
        if name == "document_codebase":
            cfg = config.resolve_config(target, {
                "out": args.get("out"), "only": args.get("only"),
                "full": args.get("full"), "offline": args.get("offline"),
            })
            rep = run_pipeline(cfg)
            out = Path(cfg.out).resolve() if cfg.out else target / "docs"
            text = (report.summarize(rep) +
                    f"\nexit_code: {rep.exit_code}\nDocs: {out}\nReport: {target / '.myagent' / 'report.json'}")
            return _text_result(text)
        if name == "analyze_codebase":
            facts = analyze_repo(target)
            summary = {
                "name": facts["repo"]["name"],
                "files": facts["repo"]["file_count"],
                "languages": facts["repo"]["languages"][:5],
                "frameworks": [f["name"] for f in facts["frameworks"]],
                "routes": len(facts["routes"]),
                "models": len(facts["models"]),
                "dependencies": len(facts["dependencies"]["runtime"]),
                "env_vars": len(facts["env_vars"]),
                "mcp_servers": sum(len(c["servers"]) for c in facts["mcp"]["configs"]),
            }
            return _text_result(json.dumps(summary, indent=2))
        if name == "get_docs_status":
            report_path = target / ".myagent" / "report.json"
            if not report_path.is_file():
                return _text_result("No docs generated yet for this target. Run document_codebase first.")
            data = json.loads(report_path.read_text(encoding="utf-8"))
            rows = [f"{d['filename']}: {d['status']} ({d['mode']}, rounds={d['rounds_used']})"
                    for d in data.get("docs", [])]
            return _text_result(f"Last run: {data.get('finished_at')}\n" + "\n".join(rows))
        return _text_result(f"unknown tool: {name}", is_error=True)
    except Exception as e:
        log.exception("tool %s failed", name)
        return _text_result(f"error: {e}", is_error=True)


def handle_message(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")

    def result(payload: dict) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "result": payload}

    if method == "initialize":
        return result({
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "myagent", "version": __version__},
        })
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return result({})
    if method == "tools/list":
        return result({"tools": TOOLS})
    if method == "tools/call":
        return result(_call_tool(msg.get("params") or {}))
    if mid is not None:
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                        format="[%(asctime)s] %(levelname)-7s %(message)s")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }) + "\n")
            sys.stdout.flush()
            continue
        resp = handle_message(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0