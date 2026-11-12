# MyAgent

Multi-agent codebase documentation generator. Point it at **any codebase** and it produces a
16-document suite detailed enough for an AI (or a human) to rebuild or extend the application —
then keeps the docs **incrementally updated** as the code changes.

- **16 worker agents**, one per document, coordinated by an orchestrator (DAG-ordered, concurrent).
- **Approver agent** reviews every document: deterministic gates (real routes/models only, no
  secrets, no broken citations) plus an LLM quality rubric, with up to 2 revision rounds.
- **Facts-first**: tables, trees, and Mermaid diagrams are rendered deterministically from static
  analysis — the LLM writes only narrative, so hard facts cannot be hallucinated.
- **Works offline** with zero configuration, or with any OpenAI-compatible API / Anthropic /
  local Ollama / LM Studio.
- **Any IDE**: MCP connector (Cursor, Claude Desktop, Windsurf, VS Code, Qoder), a skill for
  Qoder/Claude Code, and AGENTS.md for rules-based agents. See [integrations/](integrations/README.md).

Zero runtime dependencies — Python 3.10+ standard library only.

## Install from GitHub (any IDE, one command)

```bash
pip install git+https://github.com/shubham6395/MyAgen.git
```

This puts two commands on your PATH — no clone, no path configuration:

- `myagent <path-to-codebase>` — the CLI
- `myagent-mcp` — the MCP server for any IDE

Any MCP-capable IDE (Qoder, Cursor, Claude Desktop, VS Code, Windsurf) then needs only:

```json
{ "mcpServers": { "myagent": { "command": "myagent-mcp" } } }
```

(VS Code uses the `servers` key instead of `mcpServers`.) Upgrade later with
`pip install --upgrade git+https://github.com/shubham6395/MyAgen.git`.

## Quickstart

```bash
# Offline (no API key): deterministic, factual docs
python myagent.py /path/to/codebase --offline

# With an LLM (richer narrative)
export MYAGENT_PROVIDER=openai        # openai | openrouter | anthropic | ollama | lmstudio
export MYAGENT_API_KEY=sk-...
python myagent.py /path/to/codebase

# Re-run after code changes: only affected docs regenerate
python myagent.py /path/to/codebase
```

Docs are written to `<codebase>/docs/`; state lives in `<codebase>/.myagent/`.

## The document suite

| File | Contents |
|---|---|
| `README.md` | Overview, tech stack, layout, quickstart, doc index |
| `PRD.md` | Reverse-engineered product requirements (inference labeled) |
| `ARCHITECTURE.md` | Module map, component diagram, entrypoints, data flow |
| `DESIGN.md` | Design patterns, conventions, extension rules |
| `DATABASE.md` | Schema tables, ER diagram, migrations |
| `API.md` | Every endpoint: method, path, handler, auth, schemas, examples |
| `AGENTS.md` | Operating guide for AI agents working on that repo |
| `IMPLEMENTATION.md` | Subsystem walkthroughs, algorithms, extension recipes |
| `FEATURES.md` | Feature-to-code map, feature development workflow |
| `SETUP.md` | Prerequisites, env vars, install/dev/build/test commands |
| `AUTH_SECURITY.md` | Auth flows, security posture, hardening |
| `MCP.md` | MCP server configuration and connection guide |
| `INTEGRATIONS.md` | Third-party services, webhooks, env keys |
| `TESTING_QA.md` | Test inventory, strategy, how to run/add tests |
| `DEBUGGING.md` | Logging, failure surfaces, debugging playbooks |
| `BLUEPRINT.md` | **Master file**: whole-app diagrams + rebuild blueprint |

## Configuration

Precedence: CLI flags > environment variables > `myagent.config.json` > defaults.

| Env var | Meaning |
|---|---|
| `MYAGENT_PROVIDER` | `openai`, `openrouter`, `anthropic`, `ollama`, `lmstudio`, `none` |
| `MYAGENT_API_KEY` | API key (falls back to `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`) |
| `MYAGENT_MODEL` | Model id (provider default otherwise) |
| `MYAGENT_BASE_URL` | Override endpoint (any OpenAI-compatible server) |
| `MYAGENT_TIMEOUT` | Per-call timeout seconds (default 120) |
| `MYAGENT_CONTEXT_TOKENS` | Input budget per doc (default 16000) |
| `MYAGENT_MAX_OUTPUT_TOKENS` | Output budget per doc (default 8000) |

There is deliberately **no `--api-key` flag** — keys stay out of shell history.

## CLI

```
python myagent.py <path> [--out DIR] [--provider NAME] [--model M] [--base-url URL]
                         [--config FILE] [--only PRD,API.md] [--full] [--offline]
                         [--max-rounds 2] [--concurrency 4] [--dry-run]
                         [--timeout 120] [--max-retries 3] [-v|-q] [--version]
```

Exit codes: `0` success · `2` usage error · `3` analysis/IO failure · `4` completed with
flagged/degraded docs · `130` interrupted.

`--dry-run` analyzes and prints the plan (affected docs) without writing anything.
Hand-edited docs are detected and regenerated — docs are build artifacts.

## How it works

```
analyze (AST/regex/static) → CodebaseFacts → manifest diff → orchestrator
  → worker agents (draft narrative → assemble → approver → revise ≤2) → docs + report
```

The approver's deterministic gates are the hard quality bar; the LLM rubric is advisory.
A failed LLM call degrades that one document to offline rendering — the run never dies mid-suite.

## Development

```bash
python -m pip install -e .[dev]
python -m pytest tests/ -q
```

Tests use fixture repos and a FakeLLM — no network, no real API keys.
See [AGENTS.md](AGENTS.md) for architecture rules and extension recipes.