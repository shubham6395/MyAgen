from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from myagent import util

LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "go.sum", "Cargo.lock", "Gemfile.lock", "composer.lock",
}
DEV_PYPI = {"pytest", "pytest-cov", "black", "ruff", "mypy", "flake8", "isort", "coverage", "tox"}
DEV_NPM = {"jest", "vitest", "mocha", "eslint", "prettier", "typescript", "ts-node", "nodemon", "supertest"}

KNOWN_FRAMEWORKS = {
    "fastapi", "flask", "django", "express", "fastify", "next", "react", "vue",
    "svelte", "sqlalchemy", "mongoose", "sequelize", "prisma", "pytest", "jest",
    "vitest", "gin", "rails", "laravel", "actix-web", "rocket", "spring",
}

AUTH_PATTERNS = (
    ("jwt", re.compile(r"\bjwt\b|jsonwebtoken|pyjwt|python-jose|\bjose\b", re.I)),
    ("oauth", re.compile(r"\boauth|passport", re.I)),
    ("session", re.compile(r"express-session|flask[-_]login|cookie-session|express\.session", re.I)),
    ("apikey", re.compile(r"x-api-key|api[_-]?key", re.I)),
    ("basic", re.compile(r"basicAuth|basic_auth|HTTPBasic", re.I)),
)

SERVICES = {
    "stripe": ("payment", "STRIPE"), "razorpay": ("payment", "RAZORPAY"),
    "paypal": ("payment", "PAYPAL"), "twilio": ("sms", "TWILIO"),
    "sendgrid": ("email", "SENDGRID"), "@sendgrid/mail": ("email", "SENDGRID"),
    "nodemailer": ("email", "SMTP"), "openai": ("ai", "OPENAI"),
    "anthropic": ("ai", "ANTHROPIC"), "boto3": ("storage", "AWS"),
    "@aws-sdk/client-s3": ("storage", "AWS"), "firebase": ("other", "FIREBASE"),
    "firebase-admin": ("other", "FIREBASE"), "supabase": ("other", "SUPABASE"),
    "@supabase/supabase-js": ("other", "SUPABASE"), "auth0": ("other", "AUTH0"),
    "slack-sdk": ("other", "SLACK"), "posthog": ("analytics", "POSTHOG"),
    "mixpanel": ("analytics", "MIXPANEL"), "redis": ("storage", "REDIS"),
    "celery": ("other", "CELERY"),
}

ENV_READ_PY = re.compile(
    r"os\.environ\.get\(\s*[\"'](\w+)[\"']|os\.getenv\(\s*[\"'](\w+)[\"']|os\.environ\[\s*[\"'](\w+)[\"']\s*\]"
)
ENV_READ_JS = re.compile(r"process\.env\.(\w+)|process\.env\[\s*[\"'](\w+)[\"']\s*\]")
SECRET_NAME = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|PASSWD|PWD|CREDENTIAL", re.I)

MCP_NAMES = {"mcp.json", ".mcp.json", "claude_desktop_config.json", "mcp_config.json"}

CONFIG_BASENAMES = {
    ".editorconfig", "ruff.toml", ".ruff.toml", "mypy.ini", ".flake8",
    "biome.json", ".babelrc", "alembic.ini", "tsconfig.json",
}
CONFIG_GLOBS = (
    "**/.eslintrc*", "**/.prettierrc*", "**/eslint.config.*", "**/prettier.config.*",
    "**/tsconfig*.json", "**/webpack.config.*", "**/vite.config.*",
    "**/rollup.config.*", "**/.vscode/launch.json", "**/.vscode/settings.json",
)

LOG_LIBS = {
    "logging": re.compile(r"^\s*import logging|^\s*from logging", re.M),
    "loguru": re.compile(r"\bloguru\b"),
    "structlog": re.compile(r"\bstructlog\b"),
    "winston": re.compile(r"\bwinston\b"),
    "pino": re.compile(r"\bpino\b"),
    "console": re.compile(r"console\.(log|error|warn)"),
}


def run(facts: dict, texts: dict[str, str], root: Path) -> None:
    _dependencies(facts, texts)
    _frameworks(facts, texts)
    _auth(facts, texts)
    _env_vars(facts, texts)
    _mcp(facts, texts)
    _integrations(facts, texts)
    _tests(facts, texts)
    _ci(facts, texts)
    _entrypoints(facts, texts)
    _scripts(facts, texts)
    _error_handling(facts, texts)
    _logging(facts, texts)
    _config_files(facts)
    _docs_existing(facts)
    _migrations(facts, texts)
    _raw_sql_models(facts, texts)
    _prisma_models(facts, texts)
    _excerpts(facts, texts)
    _stats(facts, texts)


def _base(rel: str) -> str:
    return rel.rsplit("/", 1)[-1]


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _split_spec(line: str) -> tuple[str, str]:
    m = re.match(r"([A-Za-z0-9_.\-\[\]]+)\s*(.*)", line)
    if not m:
        return line, ""
    return m.group(1), m.group(2).strip()


def _dependencies(facts: dict, texts: dict[str, str]) -> None:
    runtime: list[dict] = []
    manifests: list[dict] = []
    for rel, text in texts.items():
        name = _base(rel)
        eco = None
        if name == "package.json":
            eco = "npm"
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {}
            for dep, spec in (data.get("dependencies") or {}).items():
                runtime.append({"name": dep, "version_spec": spec, "ecosystem": "npm", "dev": False})
            for dep, spec in (data.get("devDependencies") or {}).items():
                runtime.append({"name": dep, "version_spec": spec, "ecosystem": "npm",
                                "dev": dep in DEV_NPM or dep.startswith("@types/")})
        elif name.startswith("requirements") and name.endswith(".txt"):
            eco = "pypi"
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "-")):
                    continue
                dep, spec = _split_spec(line)
                runtime.append({"name": dep, "version_spec": spec, "ecosystem": "pypi",
                                "dev": dep.lower() in DEV_PYPI})
        elif name == "pyproject.toml":
            eco = "pypi"
            try:
                data = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                data = {}
            for spec in data.get("project", {}).get("dependencies", []):
                dep, ver = _split_spec(spec)
                runtime.append({"name": dep, "version_spec": ver, "ecosystem": "pypi",
                                "dev": dep.lower() in DEV_PYPI})
            for group in data.get("project", {}).get("optional-dependencies", {}).values():
                for spec in group:
                    dep, ver = _split_spec(spec)
                    runtime.append({"name": dep, "version_spec": ver, "ecosystem": "pypi", "dev": True})
        elif name == "go.mod":
            eco = "go"
            for m in re.finditer(r"^\s*(?:require\s+)?([\w./\-]+)\s+(v[\w.\-]+)", text, re.M):
                runtime.append({"name": m.group(1), "version_spec": m.group(2), "ecosystem": "go", "dev": False})
        elif name == "Gemfile":
            eco = "ruby"
            for m in re.finditer(r"gem\s+[\"']([^\"']+)[\"'](?:\s*,\s*[\"']([^\"']+)[\"'])?", text):
                runtime.append({"name": m.group(1), "version_spec": m.group(2) or "", "ecosystem": "ruby", "dev": False})
        elif name == "Cargo.toml":
            eco = "cargo"
            try:
                data = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                data = {}
            for dep, spec in data.get("dependencies", {}).items():
                ver = spec if isinstance(spec, str) else spec.get("version", "")
                runtime.append({"name": dep, "version_spec": ver, "ecosystem": "cargo", "dev": False})
        elif name == "composer.json":
            eco = "php"
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {}
            for dep, spec in (data.get("require") or {}).items():
                runtime.append({"name": dep, "version_spec": spec, "ecosystem": "php", "dev": False})
        if eco:
            manifests.append({"file": rel, "ecosystem": eco})
    facts["dependencies"]["runtime"] = runtime
    facts["dependencies"]["manifests"] = manifests
    facts["dependencies"]["lockfiles"] = [
        f["path"] for f in facts["files"] if _base(f["path"]) in LOCKFILES
    ]


def _frameworks(facts: dict, texts: dict[str, str]) -> None:
    found: dict[str, dict] = {}
    for dep in facts["dependencies"]["runtime"]:
        name = dep["name"].lower()
        if name in KNOWN_FRAMEWORKS:
            found[name] = {"name": name, "evidence": [m["file"] for m in facts["dependencies"]["manifests"]], "confidence": "high"}
    for imp in facts["imports"]:
        if imp["kind"] == "external":
            name = imp["target"].lower()
            if name in KNOWN_FRAMEWORKS and name not in found:
                found[name] = {"name": name, "evidence": [imp["from_file"]], "confidence": "medium"}
    facts["frameworks"] = list(found.values())


def _auth(facts: dict, texts: dict[str, str]) -> None:
    by_kind: dict[str, list[dict]] = {}
    middleware: list[str] = []
    source_files = {
        f["path"] for f in facts["files"]
        if f["role_hint"] in ("source", "script", "test")
    }
    for rel, text in texts.items():
        if rel not in source_files:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for kind, pat in AUTH_PATTERNS:
                if pat.search(line):
                    ev = by_kind.setdefault(kind, [])
                    if len(ev) < 5:
                        ev.append({"file": rel, "lineno": lineno,
                                   "snippet": util.redact_secrets(line.strip())[:120]})
                    if "middleware" in rel and rel not in middleware:
                        middleware.append(rel)
    facts["auth"]["patterns"] = [
        {"kind": k, "evidence": ev} for k, ev in by_kind.items()
    ]
    facts["auth"]["middleware"] = middleware
    facts["auth"]["protected_route_hints"] = [
        f"{r['method']} {r['path']}" for r in facts["routes"] if r.get("auth_hints")
    ]


def _env_vars(facts: dict, texts: dict[str, str]) -> None:
    records: dict[str, dict] = {}

    def rec(name: str) -> dict:
        if name not in records:
            records[name] = {"name": name, "sources": [], "default": None,
                             "secret_like": bool(SECRET_NAME.search(name))}
        return records[name]

    for rel, text in texts.items():
        base = _base(rel)
        if base in {".env.example", ".env.sample", ".env.template", "example.env"}:
            for lineno, line in enumerate(text.splitlines(), 1):
                m = re.match(r"\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*(.*)", line)
                if m:
                    r = rec(m.group(1))
                    r["sources"].append({"file": rel, "lineno": lineno, "kind": "example"})
                    r["default"] = util.redact_secrets(m.group(2).strip())
        for pat in (ENV_READ_PY, ENV_READ_JS):
            for m in pat.finditer(text):
                name = next(g for g in m.groups() if g)
                r = rec(name)
                r["sources"].append({"file": rel, "lineno": _line_of(text, m.start()), "kind": "read"})
    facts["env_vars"] = [records[k] for k in sorted(records)]


def _mcp(facts: dict, texts: dict[str, str]) -> None:
    for rel, text in texts.items():
        if _base(rel) not in MCP_NAMES and '"mcpServers"' not in text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        servers = []
        for name, cfg in (data.get("mcpServers") or {}).items():
            if not isinstance(cfg, dict):
                continue
            servers.append({
                "name": name, "command": cfg.get("command", ""),
                "args": cfg.get("args", []),
                "env_keys": sorted((cfg.get("env") or {}).keys()),
                "url": cfg.get("url", ""),
            })
        if servers:
            facts["mcp"]["configs"].append({"file": rel, "servers": servers})
    for imp in facts["imports"]:
        if imp["kind"] == "external" and imp["target"] in {"mcp", "fastmcp", "@modelcontextprotocol/sdk"}:
            facts["mcp"]["sdk_usage"].append({"file": imp["from_file"], "evidence": imp["target"]})


def _integrations(facts: dict, texts: dict[str, str]) -> None:
    found: dict[str, dict] = {}
    env_names = [e["name"] for e in facts["env_vars"]]

    def add(service: str, evidence: dict) -> None:
        kind, prefix = SERVICES[service]
        if service not in found:
            found[service] = {
                "service": service, "kind": kind, "evidence": [],
                "env_keys": [n for n in env_names if n.startswith(prefix)],
            }
        if len(found[service]["evidence"]) < 5:
            found[service]["evidence"].append(evidence)

    for dep in facts["dependencies"]["runtime"]:
        if dep["name"] in SERVICES:
            add(dep["name"], {"file": "", "lineno": 0, "import_line": f"dependency: {dep['name']} {dep['version_spec']}"})
    for imp in facts["imports"]:
        if imp["kind"] == "external" and imp["target"] in SERVICES:
            add(imp["target"], {"file": imp["from_file"], "lineno": 0,
                                "import_line": util.redact_secrets(", ".join(imp["names"]) or imp["target"])})
    facts["integrations"] = list(found.values())


def _tests(facts: dict, texts: dict[str, str]) -> None:
    frameworks: list[str] = []
    configs: list[str] = []
    dep_names = {d["name"].lower() for d in facts["dependencies"]["runtime"]}
    for fw in ("pytest", "jest", "vitest", "mocha"):
        if fw in dep_names:
            frameworks.append(fw)
    for rel in texts:
        base = _base(rel)
        if base in {"pytest.ini", "tox.ini", ".coveragerc"} or base.startswith(("jest.config", "vitest.config")):
            configs.append(rel)
            fw = "pytest" if base in {"pytest.ini", "tox.ini"} else base.split(".")[0]
            if fw not in frameworks:
                frameworks.append(fw)
        if base == "conftest.py" and "pytest" not in frameworks:
            frameworks.append("pytest")
    test_files = []
    for f in facts["files"]:
        if f["role_hint"] != "test":
            continue
        text = texts.get(f["path"], "")
        if f["language"] == "Python":
            count = len(re.findall(r"def test_", text))
        elif f["language"] == "Go":
            count = len(re.findall(r"func Test", text))
        else:
            count = len(re.findall(r"\b(?:test|it)\(", text))
        test_files.append({"file": f["path"], "test_count_estimate": count})
        if f["language"] == "Go" and "go test" not in frameworks:
            frameworks.append("go test")
    facts["tests"]["frameworks"] = frameworks
    facts["tests"]["config_files"] = configs
    facts["tests"]["test_files"] = test_files
    facts["tests"]["coverage_config"] = (
        ".coveragerc" in {_base(c) for c in configs}
        or "coverage" in dep_names or "pytest-cov" in dep_names
        or any("--cov" in t for t in texts.values())
    )


def _ci(facts: dict, texts: dict[str, str]) -> None:
    for rel, text in texts.items():
        kind = None
        if rel.startswith(".github/workflows/") and rel.endswith((".yml", ".yaml")):
            kind = "github-actions"
        elif _base(rel) == ".gitlab-ci.yml":
            kind = "gitlab"
        elif _base(rel) == "azure-pipelines.yml":
            kind = "azure"
        elif _base(rel) == "Jenkinsfile":
            kind = "jenkins"
        if not kind:
            continue
        jobs = []
        in_jobs = False
        for line in text.splitlines():
            if re.match(r"^jobs:\s*$", line):
                in_jobs = True
                continue
            if in_jobs:
                m = re.match(r"^  ([\w][\w-]*):\s*$", line)
                if m:
                    jobs.append({"name": m.group(1), "steps_summary": []})
                elif re.match(r"^\S", line):
                    in_jobs = False
        steps = [util.truncate(m.group(1).strip(), 80) for m in re.finditer(r"run:\s*(.+)", text)]
        if jobs:
            jobs[0]["steps_summary"] = steps[:10]
        facts["ci"].append({"file": rel, "kind": kind, "jobs": jobs})


def _entrypoints(facts: dict, texts: dict[str, str]) -> None:
    seen: set[str] = set()

    def add(rel: str, kind: str, evidence: str) -> None:
        if rel not in seen and len(facts["entrypoints"]) < 20:
            seen.add(rel)
            facts["entrypoints"].append({"file": rel, "kind": kind, "evidence": evidence})

    for rel, text in texts.items():
        base = _base(rel)
        if base in {"main.py", "app.py", "server.py", "manage.py", "__main__.py", "run.py"}:
            kind = "server" if re.search(r"FastAPI\(|Flask\(|app\.listen|uvicorn", text) else "main"
            add(rel, kind, base)
        elif base == "cli.py" or re.search(r"argparse|click\.command|typer", text):
            if rel.endswith(".py"):
                add(rel, "cli", "argparse/click/typer")
        elif base in {"index.js", "server.js", "app.js"} and re.search(r"listen\(|express\(", text):
            add(rel, "server", base)
        elif rel.endswith(".go") and "func main(" in text:
            add(rel, "main", "func main")
        elif rel.endswith(".py") and '__name__ == "__main__"' in text:
            add(rel, "main", "__main__ guard")


def _scripts(facts: dict, texts: dict[str, str]) -> None:
    for rel, text in texts.items():
        base = _base(rel)
        if base == "package.json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            commands = [{"name": k, "run": v} for k, v in (data.get("scripts") or {}).items()]
            if commands:
                facts["scripts"].append({"file": rel, "kind": "package-json", "commands": commands})
        elif base == "Makefile":
            commands = []
            lines = text.splitlines()
            for i, line in enumerate(lines):
                m = re.match(r"^([A-Za-z0-9][\w.-]*):(?!=)", line)
                if m:
                    run = lines[i + 1].strip() if i + 1 < len(lines) else ""
                    commands.append({"name": m.group(1), "run": run})
            if commands:
                facts["scripts"].append({"file": rel, "kind": "makefile", "commands": commands})
        elif base.startswith("Dockerfile"):
            facts["scripts"].append({"file": rel, "kind": "docker", "commands": []})
        elif rel.endswith(".sh"):
            facts["scripts"].append({"file": rel, "kind": "shell",
                                     "commands": [{"name": base, "run": f"sh {rel}"}]})


def _error_handling(facts: dict, texts: dict[str, str]) -> None:
    for rel, text in texts.items():
        patterns = []
        first = None
        checks = (
            ("try-except", re.compile(r"^\s*try:\s*$", re.M)),
            ("custom-exception", re.compile(r"class \w+\((?:\w+\.)*(?:Exception|Error)\)")),
            ("try-catch", re.compile(r"\bcatch\s*\(|\.catch\(")),
            ("error-middleware", re.compile(r"app\.use\(\s*\(?\s*err")),
        )
        for name, pat in checks:
            m = pat.search(text)
            if m:
                patterns.append(name)
                if first is None:
                    first = _line_of(text, m.start())
        if patterns and len(facts["error_handling"]) < 50:
            facts["error_handling"].append({"file": rel, "patterns": patterns, "lineno": first})


def _logging(facts: dict, texts: dict[str, str]) -> None:
    libs: dict[str, list[dict]] = {}
    for rel, text in texts.items():
        for lib, pat in LOG_LIBS.items():
            m = pat.search(text)
            if m:
                ev = libs.setdefault(lib, [])
                if len(ev) < 5:
                    ev.append({"file": rel, "lineno": _line_of(text, m.start())})
    facts["logging"]["libraries"] = list(libs.keys())
    facts["logging"]["evidence"] = [e for ev in libs.values() for e in ev]


def _config_files(facts: dict) -> None:
    out = []
    for f in facts["files"]:
        base = _base(f["path"])
        if base in CONFIG_BASENAMES or any(util.glob_match(p, f["path"]) for p in CONFIG_GLOBS):
            out.append(f["path"])
    facts["config_files"] = out


def _docs_existing(facts: dict) -> None:
    facts["docs_existing"] = [
        f["path"] for f in facts["files"] if f["role_hint"] == "docs"
    ]


def _migrations(facts: dict, texts: dict[str, str]) -> None:
    has_alembic = any(_base(r) == "alembic.ini" for r in texts)
    for rel, text in texts.items():
        base = _base(rel)
        tool = None
        if "/versions/" in f"/{rel}" and rel.endswith(".py") and (has_alembic or "alembic" in text):
            tool = "alembic"
        elif "/migrations/" in f"/{rel}" and rel.endswith(".py") and base != "__init__.py" and "django" in text.lower():
            tool = "django"
        elif "/prisma/migrations/" in f"/{rel}" and base == "migration.sql":
            tool = "prisma"
        if tool:
            dm = re.search(r'"""(.+)', text)
            summary = dm.group(1).strip() if dm else base
            facts["migrations"].append({"file": rel, "tool": tool, "summary": util.truncate(summary, 100)})


def _raw_sql_models(facts: dict, texts: dict[str, str]) -> None:
    for rel, text in texts.items():
        if not rel.endswith(".sql"):
            continue
        for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?(\w+)[\"`]?\s*\(([\s\S]*?)\);", text, re.I):
            table, body = m.group(1), m.group(2)
            fields = []
            relationships = []
            for line in body.splitlines():
                line = line.strip().rstrip(",")
                fm = re.match(r"[\"`]?(\w+)[\"`]?\s+([A-Za-z]+(?:\([\d,\s]+\))?)\s*(.*)", line)
                if not fm or fm.group(1).upper() in {"PRIMARY", "FOREIGN", "UNIQUE", "CONSTRAINT", "CHECK"}:
                    continue
                name, ftype, rest = fm.group(1), fm.group(2), fm.group(3)
                constraints = []
                pk = bool(re.search(r"PRIMARY\s+KEY", rest, re.I))
                nullable = False if re.search(r"NOT\s+NULL", rest, re.I) else None
                if re.search(r"UNIQUE", rest, re.I):
                    constraints.append("unique")
                ref = re.search(r"REFERENCES\s+(\w+)", rest, re.I)
                if ref:
                    constraints.append(f"references {ref.group(1)}")
                    relationships.append({"kind": "many-to-one", "target": ref.group(1)})
                fields.append({"name": name, "type": ftype, "nullable": nullable,
                               "primary_key": pk, "default": None, "constraints": constraints})
            if fields:
                facts["models"].append({
                    "file": rel, "lineno": _line_of(text, m.start()),
                    "orm": "raw_sql", "name": table, "table": table,
                    "fields": fields, "relationships": relationships,
                })


def _prisma_models(facts: dict, texts: dict[str, str]) -> None:
    for rel, text in texts.items():
        if _base(rel) != "schema.prisma":
            continue
        for m in re.finditer(r"model\s+(\w+)\s*\{([\s\S]*?)\}", text):
            fields = []
            for line in m.group(2).splitlines():
                fm = re.match(r"\s*(\w+)\s+([\w?\[\]]+)(.*)", line)
                if not fm:
                    continue
                constraints = []
                if "@id" in fm.group(3):
                    constraints.append("primary_key")
                if "@unique" in fm.group(3):
                    constraints.append("unique")
                fields.append({"name": fm.group(1), "type": fm.group(2),
                               "nullable": fm.group(2).endswith("?"),
                               "primary_key": "@id" in fm.group(3),
                               "default": None, "constraints": constraints})
            facts["models"].append({
                "file": rel, "lineno": _line_of(text, m.start()),
                "orm": "prisma", "name": m.group(1), "table": m.group(1),
                "fields": fields, "relationships": [],
            })


def _excerpts(facts: dict, texts: dict[str, str]) -> None:
    picks: list[tuple[str, str]] = []
    picks += [(e["file"], "entrypoint") for e in facts["entrypoints"][:2]]
    route_files = list(dict.fromkeys(r["file"] for r in facts["routes"]))
    picks += [(f, "handler") for f in route_files[:3]]
    model_files = list(dict.fromkeys(m["file"] for m in facts["models"]))
    picks += [(f, "model") for f in model_files[:2]]
    test_files = [t["file"] for t in facts["tests"]["test_files"]]
    picks += [(f, "test-sample") for f in test_files[:1]]
    for manifest in ("package.json", "pyproject.toml"):
        if manifest in texts:
            picks.append((manifest, "config"))
    total = 0
    seen: set[str] = set()
    for rel, reason in picks:
        if rel in seen or rel not in texts:
            continue
        seen.add(rel)
        text = util.truncate(util.redact_secrets(texts[rel]), 4000)
        if total + len(text) > 60000:
            break
        total += len(text)
        facts["excerpts"].append({"file": rel, "reason": reason, "text": text})


def _stats(facts: dict, texts: dict[str, str]) -> None:
    todos = []
    for rel, text in texts.items():
        for lineno, line in enumerate(text.splitlines(), 1):
            if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", line):
                todos.append({"file": rel, "lineno": lineno,
                              "text": util.redact_secrets(line.strip())[:160]})
                if len(todos) >= 100:
                    break
        if len(todos) >= 100:
            break
    facts["stats"]["todos"] = todos
    facts["stats"]["largest_files"] = [
        {"path": f["path"], "loc": f["loc"]}
        for f in sorted(facts["files"], key=lambda x: -x["loc"])[:10]
    ]