---
name: document-codebase
description: Generate or incrementally update a 16-document suite (PRD, DESIGN, ARCHITECTURE, DATABASE, API, AGENTS, README, BLUEPRINT, and implementation/setup/auth/MCP/integrations/testing/debugging guides) for any codebase using the MyAgent multi-agent tool with an approver. Use when the user asks to document a codebase, generate or create docs, produce a blueprint/architecture file, or refresh/update docs after code changes.
---

# Document a codebase with MyAgent

MyAgent analyzes a codebase and generates 16 detailed markdown documents via worker agents
(one per document) plus an approver agent. Re-running updates only the affected documents.

## 1. Locate the tool

The tool repo root is two levels above this SKILL.md (`skills/document-codebase/` → repo root).
Entry point: `<root>/myagent.py`. MCP server (alternative): `<root>/myagent_mcp.py`.

## 2. Preflight

- Check Python: `python --version` (fallback `py -3`). Requires 3.10+.
- Resolve the target codebase path from the user's request. Ask only if genuinely ambiguous.
- Check LLM availability: `MYAGENT_API_KEY` / `MYAGENT_PROVIDER` (or `OPENAI_API_KEY` /
  `ANTHROPIC_API_KEY`). If none are set, append `--offline` — the tool still produces complete
  factual docs; narrative sections become structured placeholders. Tell the user which mode ran.

## 3. Run

```bash
python "<root>/myagent.py" "<target>" [--offline] [--only PRD,API] [--full]
```

- Relay progress lines to the user (analysis counts, per-doc draft/review/revision, summary).
- LLM-mode runs on large repos can take several minutes — this is normal. For a quick interactive
  result, use `--offline` or `--only`.
- `--dry-run` first is a good idea on unfamiliar repos: it prints the plan and writes nothing.

## 4. Report

Read `<target>/.myagent/report.json` and summarize:
- verdict table (APPROVED / FLAGGED per document), revision rounds, degraded docs
- flagged docs and their unresolved issues (also appended to the doc's "Review notes")
- the docs directory path (`<target>/docs/` by default)

Exit code 4 means completed-with-flags — explain the flags; do not claim full success.
Exit code 2 = usage error, 3 = analysis/IO failure.

## 5. Incremental updates

After code changes, re-run the same command — only affected docs regenerate (hash manifest).
`--full` forces regeneration. Never hand-edit generated docs; edits are detected and overwritten.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python` not found | try `py -3`; install Python 3.10+ |
| 401/403 from provider | check `MYAGENT_API_KEY`, or run `--offline` |
| Huge repo, slow run | raise `--timeout`, lower `--concurrency`; expect truncation notes in doc footers |
| Unknown role name with `--only` | valid: README, PRD, ARCHITECTURE, DESIGN, DATABASE, API, AGENTS, IMPLEMENTATION, FEATURES, SETUP, AUTH_SECURITY, MCP, INTEGRATIONS, TESTING_QA, DEBUGGING, BLUEPRINT |
| Local model (ollama/lmstudio) | start the server first; tool probes `/models` and falls back to offline if unreachable |