---
name: document-codebase
description: Generate or incrementally update a 16-document suite (PRD, DESIGN, ARCHITECTURE, DATABASE, API, AGENTS, README, BLUEPRINT, and implementation/setup/auth/MCP/integrations/testing/debugging guides) for any codebase using the MyAgent multi-agent tool with an approver. Use when the user asks to document a codebase, generate or create docs, produce a blueprint/architecture file, or refresh/update docs after code changes.
---

# Document a codebase with MyAgent

MyAgent analyzes a codebase and generates 16 detailed markdown documents via worker agents
(one per document) plus an approver agent. Re-running updates only the affected documents.

## 1. Locate the tool

Resolve in this order and stop at the first hit:

1. `myagent` on PATH (installed via `pip install git+https://github.com/shubham6395/MyAgen.git`) —
   run `myagent "<target>" ...`; MCP server: `myagent-mcp`.
2. Repo-local script — only when this SKILL.md sits inside the MyAgent clone: the repo root is two
   levels above (`skills/document-codebase/`), so use `<root>/myagent.py`; MCP: `<root>/myagent_mcp.py`.
3. Neither found — ask the user for the MyAgent path or suggest the pip install above.

### MCP path (when the IDE already has `myagent-mcp` configured)

- `analyze_codebase {target}` — cheap preflight (languages, routes, models, deps); writes nothing.
- `document_codebase {target, only?, offline?, full?, out?}` — same pipeline as the CLI.
- `get_docs_status {target}` — last run's report; no regeneration.

## 2. Preflight

- Check Python: `python --version` (fallback `py -3`). Requires 3.10+.
- Resolve the target codebase path from the user's request. Ask only if genuinely ambiguous.
- Decide the mode from this table (precedence: CLI > env > `myagent.config.json` > defaults):

| Situation | Action |
|---|---|
| `MYAGENT_PROVIDER=ollama` or `lmstudio` | Do **not** force `--offline`. Ensure the local server runs; the tool probes `<base_url>/models` (~3 s) and falls back to offline with a warning. |
| `MYAGENT_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` set | LLM mode (`auto` picks openai, or anthropic if only that key is set). |
| `MYAGENT_PROVIDER=none`, or no key and provider `auto` | Append `--offline`. |
| `myagent.config.json` in the target or tool root | It may supply provider/model/base_url/api_key — check it before deciding. |

- If the run falls back, relay the `Falling back to OFFLINE mode: <reason>` warning.
- Offline docs are complete, but narrative sections carry `<!-- MYAGENT:NARRATIVE -->` placeholders.

## 3. Run

```bash
python "<root>/myagent.py" "<target>" [--offline] [--only PRD,API] [--full] [--dry-run]
                                      [--out DIR] [--provider NAME] [--model ID]
                                      [--max-rounds N] [--concurrency N] [--timeout S]
```

(or `myagent "<target>" ...` when installed; `--max-retries N`, `-v`, `-q` also exist.)

- `--only` accepts role IDs or filenames, case-insensitive (`PRD`, `prd.md`); an unknown name exits 2.
- `--out DIR` moves the docs, but the report stays at `<target>/.myagent/report.json`.
- Relay progress lines to the user (analysis counts, per-doc draft/review/revision, summary).
- LLM-mode runs on large repos can take several minutes — this is normal. For a quick interactive
  result, use `--offline` or `--only`.
- `--dry-run` first is a good idea on unfamiliar repos: it prints the plan and writes nothing.

## 4. Report

Read `<target>/.myagent/report.json` (or call the `get_docs_status` MCP tool) and summarize:
- `docs[].filename`, `status` (`written` / `failed`), `mode`, `rounds_used`
- `verdict.approved`; unresolved = `verdict.issues[]` with severity `blocker`/`major`
- `degraded` docs (LLM narrative failed → rendered offline)
- the docs directory path (`<target>/docs/` by default, or `--out DIR`)

Exit codes: 0 success · 2 usage error · 3 analysis/IO failure · 4 completed with flagged or
degraded docs · 130 interrupted. For 4, explain the flags; do not claim full success.
`--dry-run` writes no report.json — don't read it after a dry run.

## 5. Incremental updates

After code changes, re-run the same command — only affected documents regenerate (hash manifest).
`--full` forces regeneration. Never hand-edit generated docs; edits are detected and overwritten.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python` not found | try `py -3`; install Python 3.10+ |
| `myagent` not found | use the repo-local `<root>/myagent.py`, or `pip install git+https://github.com/shubham6395/MyAgen.git` |
| 401/403 from provider | check `MYAGENT_API_KEY`, or run `--offline` |
| Huge repo, slow run | raise `--timeout`, lower `--concurrency`; expect truncation notes in doc footers |
| Unknown role name with `--only` | valid: README, PRD, ARCHITECTURE, DESIGN, DATABASE, API, AGENTS, IMPLEMENTATION, FEATURES, SETUP, AUTH_SECURITY, MCP, INTEGRATIONS, TESTING_QA, DEBUGGING, BLUEPRINT |
| Local model (ollama/lmstudio) | start the server first; tool probes `/models` and falls back to offline if unreachable |
