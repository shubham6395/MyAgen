from __future__ import annotations

import json

from myagent import facts, util
from myagent.types import Role, Section


def S(id: str, title: str, kind: str, renderer: str | None = None,
      guidance: str = "", min_chars: int = 200, optional: bool = False) -> Section:
    return Section(id=id, title=title, kind=kind, renderer=renderer,
                   guidance=guidance, min_chars=min_chars, optional=optional)


def R(id: str, title: str, purpose: str, depends_on=(), sections=(),
      watches=(), globs=(), slice_spec=()) -> Role:
    return Role(id=id, filename=f"{id}.md", title=title, purpose=purpose,
                depends_on=tuple(depends_on), sections=tuple(sections),
                watches=tuple(watches), globs=tuple(globs),
                slice_spec=tuple(slice_spec))


ROLES: tuple[Role, ...] = (
    R("README", "README", "Project overview and entry point to the doc suite.",
      sections=(
          S("identity", "Overview", "facts", "identity_card"),
          S("about", "What this project is", "narrative",
            guidance="Explain the purpose, the problem it solves, and target users. Label inferences as inferred."),
          S("stack", "Tech stack", "facts", "tech_stack_table"),
          S("capabilities", "Key capabilities", "narrative",
            guidance="Tour the main capabilities, grounded in routes, components, and scripts."),
          S("tree", "Repository layout", "facts", "file_tree"),
          S("quickstart", "Quick start", "facts", "quickstart_commands"),
          S("usage", "Usage examples", "narrative",
            guidance="Show realistic usage examples grounded in entrypoints and scripts.", optional=True),
          S("index", "Documentation suite", "facts", "doc_index"),
      ),
      watches=("repo", "frameworks", "dependencies", "entrypoints", "scripts"),
      globs=("README*", "pyproject.toml", "package.json", "requirements*.txt"),
      slice_spec=(("repo", None), ("frameworks", None), ("dependencies", None),
                  ("entrypoints", None), ("scripts", None), ("docs_existing", None),
                  ("excerpts", "config"))),

    R("PRD", "Product Requirements (reverse-engineered)",
      "Inferred product specification, explicitly labeled as inference.",
      depends_on=("README",),
      sections=(
          S("features", "Feature inventory", "facts", "feature_inventory"),
          S("problem", "Problem statement & goals", "narrative",
            guidance="Infer the problem statement and product goals from the feature inventory. Label as inferred."),
          S("personas", "Personas (inferred)", "narrative",
            guidance="Infer likely user personas from features and integrations. Label as inferred."),
          S("functional", "Functional requirements", "narrative",
            guidance="Write functional requirements per feature, grounded in the inventory evidence."),
          S("nonfunctional", "Non-functional requirements", "narrative",
            guidance="Ground NFRs in facts: auth presence, tests, CI, error handling."),
          S("constraints", "Constraints, assumptions & out of scope", "narrative",
            guidance="State constraints and assumptions visible in the code; mark out-of-scope items."),
          S("metrics", "Success metrics (inferred)", "narrative",
            guidance="Suggest measurable success metrics. Label as inferred.", optional=True),
      ),
      watches=("routes", "symbols", "integrations", "frameworks"),
      slice_spec=(("routes", None), ("symbols", "components"), ("frameworks", None),
                  ("integrations", None), ("repo", None))),

    R("ARCHITECTURE", "Architecture", "System structure, components, and data flow.",
      depends_on=("PRD",),
      sections=(
          S("modules", "Module map", "facts", "module_map"),
          S("diagram", "Component diagram", "facts", "component_diagram"),
          S("entry", "Entrypoints", "facts", "entrypoints_table"),
          S("deps", "External dependencies", "facts", "tech_stack_table"),
          S("style", "Architecture style (inferred)", "narrative",
            guidance="Infer monolith/layered/microservice style from module map and imports. Label as inferred."),
          S("responsibilities", "Component responsibilities", "narrative",
            guidance="Describe what each major component does, citing files."),
          S("dataflow", "Request & data flow", "narrative",
            guidance="Trace a request from entrypoint through handlers to data stores."),
          S("tradeoffs", "Trade-offs & extension points", "narrative",
            guidance="Discuss design trade-offs and where the system is built to extend."),
      ),
      watches=("imports", "repo", "entrypoints", "frameworks"),
      slice_spec=(("repo", None), ("imports", None), ("entrypoints", None),
                  ("frameworks", None), ("symbols", "top_level"))),

    R("DESIGN", "Design", "Design patterns, conventions, and extension rules.",
      depends_on=("ARCHITECTURE",),
      sections=(
          S("patterns", "Pattern evidence", "facts", "pattern_evidence"),
          S("components", "UI components", "facts", "component_inventory", optional=True),
          S("observed", "Observed design patterns", "narrative",
            guidance="Name the patterns actually used (repository, middleware, MVC, ...) and where."),
          S("conventions", "Conventions", "narrative",
            guidance="Naming, error handling, and logging conventions observed in the code."),
          S("extend", "Extending the design", "narrative",
            guidance="How to add code without breaking the design; follow existing patterns."),
          S("anti", "Anti-patterns to avoid", "narrative",
            guidance="Concrete anti-patterns that would violate this codebase's design."),
      ),
      watches=("symbols", "imports", "error_handling", "logging"),
      slice_spec=(("symbols", None), ("imports", None), ("error_handling", None),
                  ("logging", None), ("frameworks", None))),

    R("DATABASE", "Database", "Schema, relationships, and migrations.",
      depends_on=("PRD",),
      sections=(
          S("models", "Schema", "facts", "model_tables"),
          S("er", "Entity relationships", "facts", "er_diagram"),
          S("migrations", "Migrations", "facts", "migrations_table"),
          S("narrative", "Data model narrative", "narrative",
            guidance="Explain the domain model and how entities relate. If no database detected, say so and stop."),
          S("access", "Access patterns", "narrative",
            guidance="Which routes/handlers read or write which models."),
          S("workflow", "Migration workflow", "narrative",
            guidance="How to create and run migrations with the detected tooling."),
          S("perf", "Indexing & performance (inferred)", "narrative",
            guidance="Indexing and performance notes grounded in schema facts. Label inferences.", optional=True),
      ),
      watches=("models", "migrations"),
      globs=("**/migrations/**", "**/*.sql", "**/schema.prisma", "**/models.py", "**/models/**"),
      slice_spec=(("models", None), ("migrations", None), ("dependencies", "db_deps"),
                  ("routes", None), ("env_vars", None))),

    R("API", "API", "Every endpoint with schemas, auth, and examples.",
      depends_on=("PRD",),
      sections=(
          S("endpoints", "Endpoints", "facts", "endpoint_tables"),
          S("schemas", "Request & response schemas", "facts", "schema_details"),
          S("overview", "API overview", "narrative",
            guidance="Summarize the API surface and style. If no routes detected, say so."),
          S("auth", "Authentication flow", "narrative",
            guidance="Explain how requests authenticate, grounded in auth evidence."),
          S("behavior", "Endpoint behavior", "narrative",
            guidance="Describe per-endpoint behavior using handler excerpts; cite file paths."),
          S("examples", "Example calls", "narrative",
            guidance="Provide example curl calls for key endpoints. Label as examples."),
          S("conventions", "Versioning & error conventions", "narrative",
            guidance="Versioning and error-response conventions observed or recommended.", optional=True),
      ),
      watches=("routes", "auth"),
      globs=("**/routes/**", "**/api/**", "**/views.py", "**/urls.py", "**/*.controller.*"),
      slice_spec=(("routes", None), ("auth", None), ("symbols", "handlers"),
                  ("excerpts", "handlers"), ("frameworks", None))),

    R("AGENTS", "Agent Guide", "Operating guide for AI agents working on this repo.",
      depends_on=("README",),
      sections=(
          S("map", "Repo map & commands", "facts", "repo_commands"),
          S("conventions", "Convention configs", "facts", "convention_configs"),
          S("guide", "Agent operating guide", "narrative",
            guidance="Where to change what, do/don't rules, and how to stay consistent with the codebase."),
          S("verify", "Verification steps", "narrative",
            guidance="Exact commands to verify changes (tests, lint, build) and doc-suite pointers."),
      ),
      watches=("repo", "scripts", "tests", "ci", "config_files"),
      globs=("AGENTS.md", "Makefile", ".editorconfig", "**/.eslintrc*", "**/ruff.toml"),
      slice_spec=(("repo", None), ("files", "dir_summary"), ("scripts", None),
                  ("tests", None), ("ci", None), ("config_files", None), ("entrypoints", None))),

    R("IMPLEMENTATION", "Project Implementation", "Module-by-module implementation walkthrough.",
      depends_on=("ARCHITECTURE",),
      sections=(
          S("inventory", "Module inventory", "facts", "module_inventory"),
          S("walkthrough", "Subsystem walkthroughs", "narrative",
            guidance="Walk through each subsystem's implementation, citing key files and symbols."),
          S("algorithms", "Key algorithms", "narrative",
            guidance="Explain the important algorithms/logic visible in excerpts."),
          S("recipes", "Extension recipes", "narrative",
            guidance="Code-level recipes for common extensions, following existing patterns."),
          S("debt", "Tech debt observations", "narrative",
            guidance="Tech debt grounded in TODOs, largest files, and parse errors."),
      ),
      watches=("symbols", "imports", "stats"),
      slice_spec=(("symbols", None), ("imports", None), ("excerpts", "top_modules"),
                  ("stats", None), ("files", "dir_summary"))),

    R("FEATURES", "Feature Development", "Feature inventory and how to build new features.",
      depends_on=("PRD",),
      sections=(
          S("map", "Feature to implementation map", "facts", "feature_map"),
          S("perfeature", "Feature guides", "narrative",
            guidance="Per-feature description and how to extend it, grounded in the map."),
          S("workflow", "Feature development workflow", "narrative",
            guidance="Workflow grounded in tests and CI: branch, implement, test, verify."),
          S("recipe", "Add a new feature", "narrative",
            guidance="Step-by-step recipe for adding a feature end-to-end in this codebase."),
      ),
      watches=("routes", "symbols", "imports", "tests"),
      slice_spec=(("routes", None), ("symbols", None), ("imports", None),
                  ("tests", None), ("integrations", None))),

    R("SETUP", "Setup & Initialization", "Prerequisites, environment, and run commands.",
      depends_on=("README",),
      sections=(
          S("prereq", "Prerequisites", "facts", "prerequisites"),
          S("env", "Environment variables", "facts", "env_table"),
          S("commands", "Install / dev / build / test", "facts", "commands_table"),
          S("init", "Step-by-step initialization", "narrative",
            guidance="Numbered setup steps grounded in the detected commands and env vars."),
          S("verify", "Verification", "narrative",
            guidance="How to verify setup worked ('you should see ...')."),
          S("trouble", "Troubleshooting (inferred)", "narrative",
            guidance="Likely setup failures and fixes. Label as inferred."),
      ),
      watches=("dependencies", "env_vars", "scripts", "ci"),
      globs=("Dockerfile*", "docker-compose*", ".env.example", "**/requirements*.txt",
             "pyproject.toml", "package.json", "Makefile"),
      slice_spec=(("dependencies", None), ("env_vars", None), ("scripts", None),
                  ("ci", None), ("entrypoints", None), ("config_files", None))),

    R("AUTH_SECURITY", "Authentication & Security", "Auth flows, posture, and hardening.",
      depends_on=("API",),
      sections=(
          S("evidence", "Auth evidence", "facts", "auth_evidence"),
          S("deps", "Security-relevant dependencies & secrets", "facts", "security_deps"),
          S("flow", "Authentication flows", "narrative",
            guidance="Explain token/session lifecycle grounded in the evidence."),
          S("posture", "Security posture (inferred)", "narrative",
            guidance="Assess strengths and gaps. Label as inferred; do not invent controls."),
          S("hardening", "Hardening recommendations", "narrative",
            guidance="Concrete hardening steps appropriate to the detected stack."),
          S("secrets", "Secrets handling", "narrative",
            guidance="How secrets are configured and how to handle them safely."),
      ),
      watches=("auth", "env_vars", "dependencies"),
      globs=("**/auth/**", "**/middleware/**", "**/security*"),
      slice_spec=(("auth", None), ("routes", None), ("env_vars", None),
                  ("dependencies", "security_deps"), ("excerpts", "handlers"))),

    R("MCP", "MCP Connection", "Model Context Protocol configuration and wiring.",
      depends_on=("SETUP",),
      sections=(
          S("inventory", "MCP configuration", "facts", "mcp_inventory"),
          S("connect", "Connection setup", "narrative",
            guidance="How to connect the detected MCP servers. If none detected, give clearly-labeled generic guidance, never presented as repo facts."),
          S("add", "Adding a server", "narrative",
            guidance="How to add a new MCP server to this project's configuration."),
          S("trouble", "Troubleshooting", "narrative",
            guidance="Common MCP connection failures and fixes."),
      ),
      watches=("mcp",),
      globs=("**/mcp.json", "**/.mcp.json", "**/claude_desktop_config.json"),
      slice_spec=(("mcp", None), ("env_vars", None), ("dependencies", None), ("scripts", None))),

    R("INTEGRATIONS", "Integrations", "Third-party services, webhooks, and configuration.",
      depends_on=("SETUP",),
      sections=(
          S("table", "Integrations", "facts", "integrations_table"),
          S("flow", "Per-integration data flow", "narrative",
            guidance="What data flows to/from each service and why."),
          S("config", "Configuration steps", "narrative",
            guidance="How to configure each integration (env keys, dashboards)."),
          S("failure", "Failure modes (inferred)", "narrative",
            guidance="Likely failure modes per integration. Label as inferred."),
          S("recipe", "Add an integration", "narrative",
            guidance="Recipe for adding a new third-party integration following existing patterns."),
      ),
      watches=("integrations", "env_vars"),
      slice_spec=(("integrations", None), ("routes", None), ("env_vars", None),
                  ("dependencies", None), ("excerpts", "handlers"))),

    R("TESTING_QA", "Testing & QA", "Test inventory, strategy, and QA gaps.",
      depends_on=("SETUP",),
      sections=(
          S("inventory", "Test inventory", "facts", "tests_inventory"),
          S("strategy", "Strategy assessment", "narrative",
            guidance="Assess the current test strategy against the codebase size and risk."),
          S("run", "Running tests", "narrative",
            guidance="Exact commands to run tests, from scripts and CI facts."),
          S("add", "Adding tests", "narrative",
            guidance="How to add tests following the pattern in the test excerpt."),
          S("gaps", "QA gaps (inferred)", "narrative",
            guidance="Coverage gaps and QA risks. Label as inferred."),
      ),
      watches=("tests", "ci"),
      globs=("**/test_*.py", "**/*_test.py", "**/tests/**", "**/*.test.*", "**/*.spec.*",
             "jest.config*", "vitest.config*", "pytest.ini", "tox.ini"),
      slice_spec=(("tests", None), ("ci", None), ("scripts", None),
                  ("dependencies", None), ("excerpts", "one_test"))),

    R("DEBUGGING", "Debugging", "Logging, failure surfaces, and debugging playbooks.",
      depends_on=("SETUP",),
      sections=(
          S("logging", "Logging & error handling", "facts", "logging_inventory"),
          S("surface", "Failure surface", "facts", "failure_surface"),
          S("playbook", "Per-subsystem debugging playbook", "narrative",
            guidance="How to debug each subsystem: where to look, what to log, how to isolate."),
          S("logs", "Log interpretation", "narrative",
            guidance="How to read the logs this codebase produces."),
          S("repro", "Reproduction recipes", "narrative",
            guidance="Steps to reproduce common failure classes locally."),
          S("perf", "Performance debugging (inferred)", "narrative",
            guidance="Performance debugging approaches for this stack. Label as inferred.", optional=True),
      ),
      watches=("error_handling", "logging", "env_vars"),
      globs=("**/logging*", "**/.vscode/**"),
      slice_spec=(("error_handling", None), ("logging", None), ("env_vars", None),
                  ("integrations", None), ("entrypoints", None), ("scripts", None))),

    R("BLUEPRINT", "Application Blueprint",
      "Single-file master blueprint: whole-app diagrams and rebuild guide.",
      depends_on=tuple(r for r in (
          "README", "PRD", "ARCHITECTURE", "DESIGN", "DATABASE", "API", "AGENTS",
          "IMPLEMENTATION", "FEATURES", "SETUP", "AUTH_SECURITY", "MCP",
          "INTEGRATIONS", "TESTING_QA", "DEBUGGING")),
      sections=(
          S("context", "System context", "facts", "system_context_diagram"),
          S("components", "Component graph", "facts", "full_component_diagram"),
          S("er", "Data model", "facts", "er_diagram"),
          S("sequence", "Representative request flow", "facts", "request_sequence"),
          S("modules", "Master module map", "facts", "module_map"),
          S("endpoints", "Endpoint index", "facts", "endpoint_index"),
          S("models", "Model index", "facts", "model_index"),
          S("env", "Environment & integrations", "facts", "env_integration_inventory"),
          S("rebuild", "Rebuild blueprint", "narrative", min_chars=400,
            guidance="Ordered build steps to recreate this application from scratch: scaffolding, data layer, API, auth, integrations, tests, deployment. Ground every step in the facts above."),
          S("wiring", "Subsystem wiring", "narrative", min_chars=300,
            guidance="How the subsystems connect: entrypoints to handlers to data stores to external services."),
          S("handoff", "AI handoff notes", "narrative",
            guidance="What an AI agent must know to regenerate or extend this application from this blueprint alone."),
      ),
      watches=tuple(facts.FACTS_KEYS),
      slice_spec=(("repo", None), ("frameworks", None), ("imports", None),
                  ("routes", None), ("models", None), ("entrypoints", None),
                  ("integrations", None), ("env_vars", None), ("dependencies", None))),
)

ROLE_BY_ID = {r.id: r for r in ROLES}
_FILENAMES = {r.filename.lower(): r for r in ROLES}


def get_role(name: str) -> Role:
    key = name.strip().upper()
    if key in ROLE_BY_ID:
        return ROLE_BY_ID[key]
    lower = name.strip().lower()
    if lower in _FILENAMES:
        return _FILENAMES[lower]
    raise KeyError(f"unknown role: {name!r} (valid: {', '.join(ROLE_BY_ID)})")


_DB_LIBS = {"sqlalchemy", "django", "prisma", "mongoose", "sequelize", "psycopg2",
            "psycopg", "pymongo", "mysqlclient", "asyncpg", "sqlite3", "alembic",
            "knex", "typeorm", "peewee", "tortoise-orm"}
_SECURITY_LIBS = {"bcrypt", "passlib", "argon2", "argon2-cffi", "helmet", "cors",
                  "pyjwt", "python-jose", "jsonwebtoken", "express-session",
                  "passport", "cryptography", "itsdangerous", "flask-login",
                  "django", "fastapi-security", "csurf"}


def _filter_top_level(facts: dict, key: str):
    if key != "symbols":
        return facts[key]
    return [s for s in facts[key] if s.get("kind") in ("class", "function")
            and "." not in s.get("qualname", "")]


def _filter_components(facts: dict, key: str):
    if key != "symbols":
        return facts[key]
    return [s for s in facts[key] if s.get("kind") == "component"]


def _filter_handlers(facts: dict, key: str):
    handlers = {r.get("handler") for r in facts["routes"] if r.get("handler")}
    route_files = {r["file"] for r in facts["routes"]}
    if key == "symbols":
        return [s for s in facts[key]
                if s.get("qualname") in handlers or s.get("file") in route_files]
    if key == "excerpts":
        return [e for e in facts[key] if e.get("reason") == "handler"]
    return facts[key]


def _filter_dir_summary(facts: dict, key: str):
    if key != "files":
        return facts[key]
    dirs: dict[str, dict] = {}
    for f in facts[key]:
        d = f["path"].rsplit("/", 1)[0] if "/" in f["path"] else "."
        agg = dirs.setdefault(d, {"dir": d, "files": 0, "loc": 0})
        agg["files"] += 1
        agg["loc"] += f.get("loc", 0)
    return sorted(dirs.values(), key=lambda x: x["dir"])


def _filter_dep_subset(names):
    def _f(facts: dict, key: str):
        if key != "dependencies":
            return facts[key]
        deps = facts[key]
        return {**deps, "runtime": [d for d in deps["runtime"] if d["name"].lower() in names]}
    return _f


def _filter_excerpts(reasons):
    def _f(facts: dict, key: str):
        if key != "excerpts":
            return facts[key]
        return [e for e in facts[key] if e.get("reason") in reasons]
    return _f


def _filter_config(facts: dict, key: str):
    if key != "excerpts":
        return facts[key]
    return [e for e in facts[key] if e.get("reason") == "config"]


def _filter_one_test(facts: dict, key: str):
    if key != "excerpts":
        return facts[key]
    return [e for e in facts[key] if e.get("reason") == "test-sample"][:1]


_FILTERS = {
    "top_level": _filter_top_level,
    "components": _filter_components,
    "handlers": _filter_handlers,
    "dir_summary": _filter_dir_summary,
    "db_deps": _filter_dep_subset(_DB_LIBS),
    "security_deps": _filter_dep_subset(_SECURITY_LIBS),
    "top_modules": _filter_excerpts({"entrypoint", "handler", "model"}),
    "handlers_excerpts": _filter_excerpts({"handler"}),
    "config": _filter_config,
    "one_test": _filter_one_test,
}

_HARD_CAPS = {"symbols": 1500, "routes": 400, "excerpts": 12}


def _collect_sources(value, acc: set[str]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("file", "from_file") and isinstance(v, str) and v:
                acc.add(v)
            else:
                _collect_sources(v, acc)
    elif isinstance(value, list):
        for item in value:
            _collect_sources(item, acc)


def build_context(role: Role, facts: dict, budget_tokens: int = 16000) -> tuple[str, list[str]]:
    """Budgeted facts slice for LLM prompts. Returns (json_context, source_files)."""
    budget_tokens = int(budget_tokens * 0.9)  # margin for outer structure

    def _dumps(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))

    payload: dict = {}
    sources: set[str] = set()
    used = 0
    for key, filter_name in role.slice_spec:
        if key not in facts:
            continue
        value = facts[key]
        if filter_name:
            value = _FILTERS[filter_name](facts, key)
        if isinstance(value, list) and key in _HARD_CAPS and len(value) > _HARD_CAPS[key]:
            value = value[:_HARD_CAPS[key]] + [{"truncated": True, "omitted": len(value) - _HARD_CAPS[key]}]
        chunk = _dumps({key: value})
        cost = util.estimate_tokens(chunk)
        if used + cost > budget_tokens:
            if isinstance(value, list) and value:
                kept = []
                for item in value:
                    item_cost = util.estimate_tokens(_dumps(item))
                    if used + item_cost + 20 > budget_tokens:
                        break
                    kept.append(item)
                    used += item_cost
                kept.append({"truncated": True, "omitted": len(value) - len(kept)})
                payload[key] = kept
                _collect_sources(kept, sources)
            continue
        payload[key] = value
        used += cost
        _collect_sources(value, sources)
    return _dumps(payload), sorted(sources)