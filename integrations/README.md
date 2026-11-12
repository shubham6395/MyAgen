# IDE integrations

MyAgent works with any AI IDE through three routes. Pick one (or combine them).

All MCP configs below point at the MCP server entry `myagent_mcp.py`.
**Replace `C:/path/to/MyAgent` with the absolute path of this repo** (forward slashes work on Windows).

## 1. MCP connector (recommended — works everywhere)

Exposes three tools to the AI: `document_codebase`, `analyze_codebase`, `get_docs_status`.

### Option A — pip install (simplest, no paths)

```bash
pip install git+https://github.com/shubham6395/MyAgen.git
```

Then every IDE config below can use `"command": "myagent-mcp"` with no `args` at all.

### Option B — run from a clone

The configs below point at the MCP server entry `myagent_mcp.py`; replace
`C:/path/to/MyAgent` with the absolute path of your clone.

### Claude Desktop
Edit `claude_desktop_config.json` (Settings → Developer → Edit Config), merge `mcpServers` from
[claude_desktop_config.example.json](claude_desktop_config.example.json). Restart Claude.

### Cursor
Create `.cursor/mcp.json` in your project (or `~/.cursor/mcp.json` globally) from
[cursor-mcp.example.json](cursor-mcp.example.json). Enable it in Settings → MCP.

### VS Code (Copilot MCP)
Create `.vscode/mcp.json` from [vscode-mcp.example.json](vscode-mcp.example.json)
(note: VS Code uses the `servers` key). Start via the MCP: List Servers command.

### Windsurf
Edit `~/.codeium/windsurf/mcp_config.json`, merge `mcpServers` from
[windsurf-mcp.example.json](windsurf-mcp.example.json).

### Qoder
Settings → MCP → add server: command `python`, args `["C:/path/to/MyAgent/myagent_mcp.py"]`.

Then just ask the AI: *"document this codebase"* or *"refresh the docs"*.

## 2. Skill (Qoder / Claude Code)

Copy `skills/document-codebase/` into:
- **Qoder**: your skills directory (project `.qoder/skills/` or user skills)
- **Claude Code**: `~/.claude/skills/` (global) or `.claude/skills/` (project)

The skill teaches the agent to run the CLI, relay progress, and summarize the approver report.

## 3. AGENTS.md (rules-based agents: Codex, Cursor, etc.)

The tool *generates* an `AGENTS.md` inside the target codebase's `docs/` — any agent that reads
AGENTS.md-style rules can follow it. For this repo itself, see the root [AGENTS.md](../AGENTS.md).

## Environment (optional, for LLM mode)

```bash
MYAGENT_PROVIDER=openai        # openai | openrouter | anthropic | ollama | lmstudio
MYAGENT_API_KEY=sk-...
MYAGENT_MODEL=gpt-4o-mini      # optional override
```

Without a key, everything still works in `--offline` mode (factual docs, placeholder narrative).