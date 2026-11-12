# AGENTS.md — MyAgent

MyAgent is a multi-agent codebase documentation generator: 16 worker agents (one per document),
an orchestrator, and an approver agent. It analyzes any repo into `CodebaseFacts`, renders
deterministic facts sections, and uses an LLM only for narrative sections.

## Hard rules

- **Stdlib only at runtime.** No third-party runtime imports. pytest is the only dev dependency.
- **No network in tests.** Use `tests/fakes.py` (FakeLLM) and monkeypatched `myagent.llm.urlopen`.
- **UTF-8 everywhere; posix relative paths in data.** Never store absolute paths in facts/manifest
  output that lands in docs. Console output is ASCII. Windows-first (pathlib, no shell assumptions).
- **MCP stdout purity.** `myagent/mcp_server.py` writes only JSON-RPC to stdout; all logging to stderr.
- **Secrets:** never read `.env` values (only `.env.example` defaults); env var NAMES only;
  `util.redact_secrets()` on any captured code snippet; no `--api-key` CLI flag.
- **Facts are dicts, control plane is dataclasses.** The facts schema lives in `myagent/facts.py`;
  bump `SCHEMA_VERSION` on any breaking change (forces full regeneration).
- Render functions are pure: `(facts, role) -> markdown`. No I/O, no LLM calls in renderers.
- Use `logging`, not `print` (CLI user-facing output excepted). `from __future__ import annotations`.

## Layout

- `myagent.py` / `myagent_mcp.py` — thin entries (CLI / MCP stdio server)
- `myagent/analyzer/` — walker (gitignore engine), python (ast), javascript (regex), generic, detect
- `myagent/facts.py` — CodebaseFacts contract; `roles.py` — 16 role definitions + budgeted slicer
- `myagent/render/` — deterministic sections, offline narrator, assembler
- `myagent/llm.py` — OpenAI-compatible / Anthropic / Null clients (urllib)
- `myagent/agents.py` — Worker draft/revise; `approver.py` — D01–D08 gates + LLM rubric
- `myagent/orchestrator.py` — DAG levels + ThreadPoolExecutor; `updater.py` — manifest/impact
- `myagent/cli.py` — argparse + `run_pipeline(cfg)` (shared with MCP); `report.py` — summary/report.json
- `tests/` — fixtures (fastapi_app, express_app, polyglot_repo), goldens, fakes

## Commands

```bash
python myagent.py <path> --offline     # run
python -m pytest tests/ -q             # test suite
python myagent.py . --offline          # dogfood
```

## Extension recipes

- **Add a document role:** add a `R(...)` entry in `roles.py` (sections, watches, globs, slice_spec),
  add renderer keys to `render/sections.py` + registry, guidance text is inline in the role.
  Add tests to `test_roles.py` integrity checks happen automatically.
- **Add a language extractor:** new module in `analyzer/`, register in `analyzer/__init__.py`,
  emit standard symbol/import records, never raise (fall back to `generic.py`).
- **Add an MCP tool:** append to `TOOLS` in `mcp_server.py` + handle in `_call_tool`; keep stdout pure.

## Conventions

- TDD: write the failing test first (`tests/test_*.py`), then implement.
- Approver deterministic checks are the quality gate; LLM review failure must never flag a doc.
- Generated docs are build artifacts: hand edits are detected via sha drift and regenerated.