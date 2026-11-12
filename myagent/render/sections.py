from __future__ import annotations

import re
from collections import Counter

from myagent.types import Role


def _table(headers: list[str], rows: list[list]) -> str:
    def esc(x) -> str:
        return str(x).replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(esc(c) for c in row) + " |")
    return "\n".join(out)


def _mermaid(body: str) -> str:
    return "```mermaid\n" + body.strip() + "\n```"


def _node(path: str) -> str:
    return re.sub(r"\W", "_", path)


def _loc(rec: dict) -> str:
    return f"{rec.get('file', '')}:{rec.get('lineno', 0)}"


def _cap(lines: list[str], limit: int = 200) -> str:
    if len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join(lines[:limit]) + f"\n... ({len(lines) - limit} more entries)"


def _features(facts: dict) -> list[dict]:
    groups: dict[str, dict] = {}
    for r in facts["routes"]:
        seg = r["path"].strip("/").split("/")[0] or "root"
        seg = re.sub(r"[{}:]", "", seg)
        g = groups.setdefault(f"api:{seg}", {"name": seg, "kind": "api", "evidence": []})
        g["evidence"].append(f"{r['method']} {r['path']} ({_loc(r)})")
    for s in facts["symbols"]:
        if s.get("kind") == "component":
            g = groups.setdefault(f"ui:{s['name']}", {"name": s["name"], "kind": "ui", "evidence": []})
            g["evidence"].append(_loc(s))
    for e in facts["entrypoints"]:
        if e["kind"] == "cli":
            g = groups.setdefault(f"cli:{e['file']}", {"name": e["file"], "kind": "cli", "evidence": []})
            g["evidence"].append(_loc(e))
    return list(groups.values())


def identity_card(facts: dict, role: Role) -> str:
    repo = facts["repo"]
    fw = ", ".join(f["name"] for f in facts["frameworks"]) or "none detected"
    size_kb = repo["total_bytes"] / 1024
    return (
        f"- **Name:** {repo['name']}\n"
        f"- **Primary language:** {repo['primary_language'] or 'unknown'}\n"
        f"- **Files:** {repo['file_count']} ({size_kb:.1f} KB)\n"
        f"- **Frameworks:** {fw}"
    )


def tech_stack_table(facts: dict, role: Role) -> str:
    deps = facts["dependencies"]["runtime"]
    if not deps:
        return "No dependency manifests detected."
    rows = [[d["name"], d["version_spec"], d["ecosystem"], "dev" if d["dev"] else "runtime"]
            for d in deps[:100]]
    note = f"\n\n... ({len(deps) - 100} more dependencies)" if len(deps) > 100 else ""
    return _table(["Dependency", "Version", "Ecosystem", "Kind"], rows) + note


def file_tree(facts: dict, role: Role) -> str:
    files = facts["files"]
    if not files:
        return "No files found."
    root = facts["repo"]["name"] or "repo"
    root_files: list[str] = []
    dirs: dict[str, list[str]] = {}
    for f in files:
        parts = f["path"].split("/")
        if len(parts) == 1:
            root_files.append(parts[0])
        else:
            dirs.setdefault(parts[0], []).append(f["path"])
    lines = [f"{root}/"]
    lines += [f"  {n}" for n in sorted(root_files)]
    for d in sorted(dirs):
        paths = dirs[d]
        lines.append(f"  {d}/ ({len(paths)} files)")
        subdirs: dict[str, int] = {}
        for p in sorted(paths):
            parts = p.split("/")
            if len(parts) == 2:
                lines.append(f"    {parts[1]}")
            else:
                subdirs[parts[1]] = subdirs.get(parts[1], 0) + 1
        for sd in sorted(subdirs):
            lines.append(f"    {sd}/ ({subdirs[sd]} files)")
    return "```\n" + _cap(lines) + "\n```"


def quickstart_commands(facts: dict, role: Role) -> str:
    rows = []
    for s in facts["scripts"]:
        for c in s["commands"]:
            rows.append([c["name"], f"`{c['run']}`", s["file"]])
    for e in facts["entrypoints"][:5]:
        rows.append([e["kind"], f"see `{e['file']}`", e["file"]])
    if not rows:
        return "No run commands detected."
    return _table(["Purpose", "Command", "Source"], rows)


def doc_index(facts: dict, role: Role) -> str:
    from myagent.roles import ROLES
    return "\n".join(
        f"- [{r.filename}]({r.filename}) — {r.title}"
        for r in ROLES if r.id != role.id
    )


def feature_inventory(facts: dict, role: Role) -> str:
    feats = _features(facts)
    if not feats:
        return "No features detected (no routes, components, or CLI entrypoints)."
    rows = [[g["name"], g["kind"], "; ".join(g["evidence"][:4])] for g in feats]
    return _table(["Feature", "Kind", "Evidence"], rows)


def module_map(facts: dict, role: Role) -> str:
    dirs: dict[str, dict] = {}
    for f in facts["files"]:
        d = f["path"].split("/")[0] if "/" in f["path"] else "."
        agg = dirs.setdefault(d, {"files": 0, "loc": 0, "symbols": 0})
        agg["files"] += 1
        agg["loc"] += f.get("loc", 0)
    for s in facts["symbols"]:
        d = s["file"].split("/")[0] if "/" in s["file"] else "."
        if d in dirs:
            dirs[d]["symbols"] += 1
    if not dirs:
        return "No modules detected."
    rows = [[d, a["files"], a["loc"], a["symbols"]] for d, a in sorted(dirs.items())]
    return _table(["Module", "Files", "LOC", "Symbols"], rows)


def _import_edges(facts: dict) -> list[tuple[str, str]]:
    return [(i["from_file"], i["target"]) for i in facts["imports"]
            if i["kind"] == "internal" and i["from_file"] != i["target"]]


def component_diagram(facts: dict, role: Role) -> str:
    edges = _import_edges(facts)
    if not edges:
        return "No internal import edges detected."
    degree: Counter = Counter()
    for a, b in edges:
        degree[a] += 1
        degree[b] += 1
    top = {n for n, _ in degree.most_common(25)}
    lines = ["graph LR"]
    for n in sorted(top):
        lines.append(f'  {_node(n)}["{n.rsplit("/", 1)[-1]}"]')
    for a, b in sorted(set(edges)):
        if a in top and b in top:
            lines.append(f"  {_node(a)} --> {_node(b)}")
    return _mermaid("\n".join(lines))


def entrypoints_table(facts: dict, role: Role) -> str:
    if not facts["entrypoints"]:
        return "No entrypoints detected."
    rows = [[e["file"], e["kind"], e["evidence"]] for e in facts["entrypoints"]]
    return _table(["File", "Kind", "Evidence"], rows)


def pattern_evidence(facts: dict, role: Role) -> str:
    decs: Counter = Counter()
    bases: Counter = Counter()
    for s in facts["symbols"]:
        for d in s.get("decorators", []):
            decs[d.split("(")[0]] += 1
        for b in s.get("bases", []):
            bases[b] += 1
    parts = []
    if decs:
        parts.append(_table(["Decorator", "Uses"], [[d, c] for d, c in decs.most_common(10)]))
    if bases:
        parts.append(_table(["Base class", "Uses"], [[b, c] for b, c in bases.most_common(10)]))
    if facts["auth"]["middleware"]:
        parts.append("Auth middleware: " + ", ".join(f"`{m}`" for m in facts["auth"]["middleware"]))
    return "\n\n".join(parts) if parts else "No pattern evidence detected."


def component_inventory(facts: dict, role: Role) -> str:
    comps = [s for s in facts["symbols"] if s.get("kind") == "component"]
    if not comps:
        return "No UI components detected."
    rows = [[s["name"], _loc(s)] for s in comps[:100]]
    return _table(["Component", "Location"], rows)


def model_tables(facts: dict, role: Role) -> str:
    models = facts["models"]
    if not models:
        return ("No database detected — searched: ORM models (SQLAlchemy, Django, Prisma, "
                "Mongoose, Sequelize) and raw .sql schemas.")
    parts = []
    for m in models:
        parts.append(f"### {m['name']} (`{m['table']}`, {m['orm']}) — {_loc(m)}")
        if m["fields"]:
            rows = [[f["name"], f["type"],
                     "no" if f["nullable"] is False else ("yes" if f["nullable"] else ""),
                     "PK" if f["primary_key"] else "",
                     f["default"] if f["default"] is not None else "",
                     ", ".join(f["constraints"])] for f in m["fields"]]
            parts.append(_table(["Field", "Type", "Nullable", "Key", "Default", "Constraints"], rows))
        else:
            parts.append("No fields extracted.")
    return "\n\n".join(parts)


def er_diagram(facts: dict, role: Role) -> str:
    models = facts["models"]
    if not models:
        return "No entities detected."
    by_name = {m["name"].lower(): m for m in models}
    lines = ["erDiagram"]
    for m in models:
        lines.append(f"  {m['table']} {{")
        for f in m["fields"][:12]:
            ftype = re.sub(r"\W", "", f["type"]) or "unknown"
            lines.append(f"    {ftype} {f['name']}")
        lines.append("  }")
    for m in models:
        for rel in m.get("relationships", []):
            target = by_name.get(str(rel.get("target", "")).lower())
            if not target:
                continue
            arrow = {"one-to-many": "||--o{", "many-to-one": "}o--||",
                     "many-to-many": "}o--o{"}.get(rel.get("kind", ""), "||--o{")
            lines.append(f"  {m['table']} {arrow} {target['table']} : relates")
    return _mermaid("\n".join(lines))


def migrations_table(facts: dict, role: Role) -> str:
    if not facts["migrations"]:
        return "No migrations detected."
    rows = [[m["file"], m["tool"], m["summary"]] for m in facts["migrations"]]
    return _table(["File", "Tool", "Summary"], rows)


def endpoint_tables(facts: dict, role: Role) -> str:
    routes = facts["routes"]
    if not routes:
        return ("No HTTP routes detected — searched FastAPI, Flask, Django, Express, "
                "Fastify, and Next.js route patterns.")
    by_file: dict[str, list[dict]] = {}
    for r in routes:
        by_file.setdefault(r["file"], []).append(r)
    parts = []
    for file, rs in sorted(by_file.items()):
        parts.append(f"### `{file}`")
        rows = [[r["method"], f"`{r['path']}`", r.get("handler") or "",
                 f"{file}:{r.get('lineno', 0)}",
                 ", ".join(r.get("auth_hints") or []) or "—",
                 " / ".join(x for x in (r.get("request_model"), r.get("response_model")) if x) or "—"]
                for r in rs]
        parts.append(_table(["Method", "Path", "Handler", "Location", "Auth", "Req / Resp"], rows))
    return "\n\n".join(parts)


def schema_details(facts: dict, role: Role) -> str:
    names = set()
    for r in facts["routes"]:
        for k in ("request_model", "response_model"):
            if r.get(k):
                names.add(r[k])
    if not names:
        return "No request/response models detected."
    parts = []
    for name in sorted(names):
        model = next((m for m in facts["models"] if m["name"] == name), None)
        if model:
            rows = [[f["name"], f["type"]] for f in model["fields"]]
            parts.append(f"### {name}\n" + _table(["Field", "Type"], rows))
            continue
        sym = next((s for s in facts["symbols"] if s["name"] == name), None)
        if sym:
            parts.append(f"### {name}\n`{sym.get('signature') or sym['kind']}` — {_loc(sym)}")
    return "\n\n".join(parts) if parts else "No request/response models detected."


def repo_commands(facts: dict, role: Role) -> str:
    parts = [module_map(facts, role)]
    cmds = quickstart_commands(facts, role)
    parts.append("### Commands\n" + cmds)
    if facts["tests"]["frameworks"]:
        parts.append("Test frameworks: " + ", ".join(facts["tests"]["frameworks"]))
    return "\n\n".join(parts)


def convention_configs(facts: dict, role: Role) -> str:
    if not facts["config_files"]:
        return "No lint/format/type configuration files detected."
    return "\n".join(f"- `{p}`" for p in facts["config_files"])


def module_inventory(facts: dict, role: Role) -> str:
    parts = [module_map(facts, role)]
    largest = facts["stats"]["largest_files"]
    if largest:
        parts.append("### Largest files\n" + _table(
            ["File", "LOC"], [[f["path"], f["loc"]] for f in largest]))
    degree: Counter = Counter()
    for a, b in _import_edges(facts):
        degree[a] += 1
        degree[b] += 1
    if degree:
        parts.append("### Most connected modules\n" + _table(
            ["File", "Connections"], [[n, c] for n, c in degree.most_common(10)]))
    return "\n\n".join(parts)


def feature_map(facts: dict, role: Role) -> str:
    feats = _features(facts)
    if not feats:
        return "No features detected."
    rows = [[g["name"], g["kind"], "; ".join(g["evidence"][:6])] for g in feats]
    return _table(["Feature", "Kind", "Implementation evidence"], rows)


def prerequisites(facts: dict, role: Role) -> str:
    langs = facts["repo"]["languages"]
    parts = []
    if langs:
        parts.append(_table(["Language", "Files", "Share"],
                            [[l["lang"], l["files"], f"{l['pct']}%"] for l in langs[:10]]))
    ecosystems = sorted({m["ecosystem"] for m in facts["dependencies"]["manifests"]})
    if ecosystems:
        parts.append("Package ecosystems: " + ", ".join(ecosystems))
    return "\n\n".join(parts) if parts else "No prerequisites detected."


def env_table(facts: dict, role: Role) -> str:
    env = facts["env_vars"]
    if not env:
        return "No environment variables detected."
    rows = [[e["name"], e["default"] if e["default"] is not None else "",
             "yes" if e["secret_like"] else "",
             "; ".join(f"{s['file']}:{s['lineno']} ({s['kind']})" for s in e["sources"][:3])]
            for e in env]
    return _table(["Variable", "Default (example)", "Secret-like", "Sources"], rows)


def commands_table(facts: dict, role: Role) -> str:
    parts = []
    rows = []
    for s in facts["scripts"]:
        for c in s["commands"]:
            rows.append([c["name"], f"`{c['run']}`", s["kind"], s["file"]])
    test_cmds = {"pytest": "python -m pytest", "jest": "npm test",
                 "vitest": "npx vitest", "mocha": "npx mocha", "go test": "go test ./..."}
    has_test = any(r[0] == "test" for r in rows)
    for fw in facts["tests"]["frameworks"]:
        if fw in test_cmds and not has_test:
            rows.append(["test", f"`{test_cmds[fw]}`", "test-framework", fw])
            has_test = True
    if rows:
        parts.append(_table(["Command", "Run", "Kind", "Source"], rows))
    if facts["ci"]:
        ci_rows = [[c["file"], c["kind"], ", ".join(j["name"] for j in c["jobs"])] for c in facts["ci"]]
        parts.append("### CI\n" + _table(["File", "Kind", "Jobs"], ci_rows))
    return "\n\n".join(parts) if parts else "No commands detected."


def auth_evidence(facts: dict, role: Role) -> str:
    auth = facts["auth"]
    if not auth["patterns"]:
        return "No authentication patterns detected in source files."
    rows = []
    for p in auth["patterns"]:
        for ev in p["evidence"][:3]:
            rows.append([p["kind"], f"{ev['file']}:{ev['lineno']}", ev["snippet"]])
    parts = [_table(["Pattern", "Location", "Evidence"], rows)]
    if auth["protected_route_hints"]:
        parts.append("Protected routes: " + ", ".join(f"`{r}`" for r in auth["protected_route_hints"]))
    return "\n\n".join(parts)


def security_deps(facts: dict, role: Role) -> str:
    from myagent.roles import _SECURITY_LIBS
    deps = [d for d in facts["dependencies"]["runtime"] if d["name"].lower() in _SECURITY_LIBS]
    secrets = [e["name"] for e in facts["env_vars"] if e["secret_like"]]
    parts = []
    if deps:
        parts.append(_table(["Dependency", "Version"], [[d["name"], d["version_spec"]] for d in deps]))
    if secrets:
        parts.append("Secret-like variables (names only): " + ", ".join(f"`{n}`" for n in secrets))
    return "\n\n".join(parts) if parts else "No security-relevant dependencies or secret variables detected."


def mcp_inventory(facts: dict, role: Role) -> str:
    configs = facts["mcp"]["configs"]
    if not configs:
        return ("No MCP configuration detected — searched mcp.json, .mcp.json, "
                "claude_desktop_config.json, and MCP SDK imports.")
    parts = []
    for cfg in configs:
        rows = [[s["name"], s["command"], " ".join(s["args"]),
                 ", ".join(s["env_keys"]) or "—", s["url"] or "—"] for s in cfg["servers"]]
        parts.append(f"### `{cfg['file']}`\n" + _table(
            ["Server", "Command", "Args", "Env keys", "URL"], rows))
    return "\n\n".join(parts)


def integrations_table(facts: dict, role: Role) -> str:
    integ = facts["integrations"]
    parts = []
    if integ:
        rows = [[i["service"], i["kind"],
                 "; ".join(e.get("import_line", "") for e in i["evidence"][:2]),
                 ", ".join(i["env_keys"]) or "—"] for i in integ]
        parts.append(_table(["Service", "Kind", "Evidence", "Env keys"], rows))
    webhooks = [r for r in facts["routes"] if "webhook" in r["path"].lower()]
    if webhooks:
        parts.append("### Webhook candidates\n" + _table(
            ["Method", "Path", "Location"],
            [[r["method"], f"`{r['path']}`", _loc(r)] for r in webhooks]))
    return "\n\n".join(parts) if parts else "No third-party integrations detected."


def tests_inventory(facts: dict, role: Role) -> str:
    t = facts["tests"]
    parts = []
    parts.append("Frameworks: " + (", ".join(t["frameworks"]) or "none detected"))
    if t["config_files"]:
        parts.append("Configs: " + ", ".join(f"`{c}`" for c in t["config_files"]))
    if t["test_files"]:
        parts.append(_table(["Test file", "Est. tests"],
                            [[f["file"], f["test_count_estimate"]] for f in t["test_files"][:50]]))
    else:
        parts.append("No test files detected.")
    parts.append(f"Coverage config: {'yes' if t['coverage_config'] else 'no'}")
    return "\n\n".join(parts)


def logging_inventory(facts: dict, role: Role) -> str:
    parts = []
    log = facts["logging"]
    parts.append("Logging libraries: " + (", ".join(log["libraries"]) or "none detected"))
    if log["evidence"]:
        parts.append(_table(["Library evidence", "Location"],
                            [["", f"{e['file']}:{e['lineno']}"] for e in log["evidence"][:8]]))
    if facts["error_handling"]:
        parts.append("### Error handling\n" + _table(
            ["File", "Patterns", "Line"],
            [[e["file"], ", ".join(e["patterns"]), e["lineno"]] for e in facts["error_handling"][:20]]))
    return "\n\n".join(parts)


def failure_surface(facts: dict, role: Role) -> str:
    rows = []
    for e in facts["env_vars"]:
        rows.append(["config", e["name"], "missing/invalid value"])
    for i in facts["integrations"]:
        rows.append(["integration", i["service"], "external API failure"])
    for e in facts["entrypoints"]:
        rows.append(["entrypoint", e["file"], "startup failure"])
    if not rows:
        return "No failure surface detected."
    return _table(["Kind", "Component", "Typical failure"], rows[:40])


def system_context_diagram(facts: dict, role: Role) -> str:
    repo = facts["repo"]["name"] or "app"
    lines = ["graph TD", f'  user(["User / Client"])', f'  app["{repo}"]']
    lines.append("  user --> app")
    for e in facts["entrypoints"][:4]:
        lines.append(f'  {_node(e["file"])}["{e["file"]}"]')
        lines.append(f"  app --> {_node(e['file'])}")
    if facts["models"]:
        lines.append('  db[("Database")]')
        lines.append("  app --> db")
    for i in facts["integrations"][:8]:
        lines.append(f'  svc_{_node(i["service"])}["{i["service"]}"]')
        lines.append(f"  app --> svc_{_node(i['service'])}")
    return _mermaid("\n".join(lines))


def full_component_diagram(facts: dict, role: Role) -> str:
    edges = _import_edges(facts)
    if not edges:
        return "No internal import edges detected."
    nodes = sorted({n for e in edges for n in e})[:60]
    keep = set(nodes)
    lines = ["graph LR"]
    for n in nodes:
        lines.append(f'  {_node(n)}["{n.rsplit("/", 1)[-1]}"]')
    for a, b in sorted(set(edges)):
        if a in keep and b in keep:
            lines.append(f"  {_node(a)} --> {_node(b)}")
    return _mermaid("\n".join(lines))


def request_sequence(facts: dict, role: Role) -> str:
    if not facts["routes"]:
        return "No request flow detected (no HTTP routes)."
    r = facts["routes"][0]
    handler = _node(r["file"])
    lines = ["sequenceDiagram", f"  Client->>{handler}: {r['method']} {r['path']}"]
    if facts["models"]:
        lines.append(f"  {handler}->>Database: query (inferred)")
        lines.append(f"  Database-->>{handler}: rows")
    lines.append(f"  {handler}-->>Client: response")
    return _mermaid("\n".join(lines))


def endpoint_index(facts: dict, role: Role) -> str:
    if not facts["routes"]:
        return "No HTTP routes detected."
    rows = [[r["method"], f"`{r['path']}`", _loc(r)] for r in facts["routes"][:400]]
    return _table(["Method", "Path", "Location"], rows)


def model_index(facts: dict, role: Role) -> str:
    if not facts["models"]:
        return "No data models detected."
    rows = [[m["name"], m["table"], m["orm"], len(m["fields"]), _loc(m)]
            for m in facts["models"]]
    return _table(["Model", "Table", "ORM", "Fields", "Location"], rows)


def env_integration_inventory(facts: dict, role: Role) -> str:
    parts = []
    env = facts["env_vars"]
    parts.append("Environment variables: " + (", ".join(f"`{e['name']}`" for e in env) or "none"))
    integ = facts["integrations"]
    parts.append("Integrations: " + (", ".join(i["service"] for i in integ) or "none"))
    return "\n\n".join(parts)