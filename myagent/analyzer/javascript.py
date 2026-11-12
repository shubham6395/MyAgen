from __future__ import annotations

import re

RE_REQUIRE = re.compile(
    r"(?:(?:const|let|var)\s+([\w$]+)\s*=\s*)?require\(\s*[\"']([^\"']+)[\"']\s*\)"
)
RE_IMPORT = re.compile(r"import\s+(?:[\w*{},\s]+\s+from\s+)?[\"']([^\"']+)[\"']")
RE_ROUTE = re.compile(
    r"\b(?:app|router|server)\.(get|post|put|delete|patch|all|options|head)\(\s*[\"'`]([^\"'`]+)[\"'`]"
)
RE_MOUNT = re.compile(r"\bapp\.use\(\s*[\"'`]([^\"'`]+)[\"'`]\s*,\s*(\w+)\s*\)")
RE_FUNC = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)")
RE_ARROW = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>")
RE_CLASS = re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)(?:\s+extends\s+([\w.]+))?")
RE_IFACE = re.compile(r"\binterface\s+([A-Za-z_$][\w$]*)")
RE_TYPE = re.compile(r"\btype\s+([A-Za-z_$][\w$]*)\s*=")
RE_MODEL = re.compile(r"mongoose\.model\(\s*[\"'](\w+)[\"']")
RE_SCHEMA = re.compile(r"new\s+mongoose\.Schema\(\s*\{([\s\S]*?)\}\s*\)")
RE_DEFINE = re.compile(r"sequelize\.define\(\s*[\"'](\w+)[\"']\s*,\s*\{([\s\S]*?)\}\s*\)")
RE_FIELD_OBJ = re.compile(r"(\w+)\s*:\s*\{([^}]*)\}")
RE_FIELD_SHORT = re.compile(r"(\w+)\s*:\s*(String|Number|Boolean|Date|Buffer|ObjectId|Mixed)\b")


def _lineno(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _framework(rel: str, text: str) -> str:
    if re.search(r"(?:require\(\s*[\"']express[\"']|from\s+[\"']express[\"'])", text):
        return "express"
    if re.search(r"(?:require\(\s*[\"']fastify[\"']|from\s+[\"']fastify[\"'])", text):
        return "fastify"
    if "/pages/api/" in f"/{rel}" or "/app/api/" in f"/{rel}":
        return "next"
    return "generic"


def _symbol(rel, text, m, kind, name, signature="") -> dict:
    return {
        "file": rel, "lineno": _lineno(text, m.start()),
        "end_lineno": _lineno(text, m.end()),
        "kind": kind, "name": name, "qualname": name,
        "signature": signature, "docstring": "", "decorators": [],
        "bases": [], "exported": True,
    }


def extract(rel: str, text: str) -> dict:
    out = {"symbols": [], "imports": [], "routes": [], "models": [], "mounts": []}
    framework = _framework(rel, text)
    is_jsx = rel.endswith((".jsx", ".tsx")) or "React" in text

    var_sources: dict[str, str] = {}
    for m in RE_REQUIRE.finditer(text):
        var, source = m.group(1), m.group(2)
        if var:
            var_sources[var] = source
        kind = "internal" if source.startswith(".") else "external"
        target = source if kind == "internal" else _package(source)
        out["imports"].append({
            "from_file": rel, "target": target, "kind": kind,
            "names": [var] if var else [],
        })
    for m in RE_IMPORT.finditer(text):
        source = m.group(1)
        kind = "internal" if source.startswith(".") else "external"
        target = source if kind == "internal" else _package(source)
        out["imports"].append({"from_file": rel, "target": target, "kind": kind, "names": []})

    for m in RE_ROUTE.finditer(text):
        method, path = m.group(1).upper(), m.group(2)
        rest = text[m.end():text.find("\n", m.end()) if text.find("\n", m.end()) != -1 else len(text)]
        auth_hints = [w for w in re.findall(r"\b(\w*auth\w*)\b", rest, re.I)]
        out["routes"].append({
            "file": rel, "lineno": _lineno(text, m.start()),
            "framework": framework, "method": method, "path": path,
            "handler": "", "auth_hints": auth_hints,
            "request_model": None, "response_model": None,
        })

    for m in RE_MOUNT.finditer(text):
        prefix, var = m.group(1), m.group(2)
        out["mounts"].append({
            "file": rel, "prefix": prefix, "var": var,
            "source": var_sources.get(var, ""),
        })

    for m in RE_FUNC.finditer(text):
        name = m.group(1)
        kind = "component" if is_jsx and name[0].isupper() else "function"
        out["symbols"].append(_symbol(rel, text, m, kind, name, f"({m.group(2)})"))
    for m in RE_ARROW.finditer(text):
        name = m.group(1)
        kind = "component" if is_jsx and name[0].isupper() else "function"
        out["symbols"].append(_symbol(rel, text, m, kind, name, f"({m.group(2)})"))
    for m in RE_CLASS.finditer(text):
        name, base = m.group(1), m.group(2) or ""
        kind = "component" if base.endswith("Component") else "class"
        rec = _symbol(rel, text, m, kind, name)
        rec["bases"] = [base] if base else []
        out["symbols"].append(rec)
    for m in RE_IFACE.finditer(text):
        out["symbols"].append(_symbol(rel, text, m, "interface", m.group(1)))
    for m in RE_TYPE.finditer(text):
        out["symbols"].append(_symbol(rel, text, m, "type", m.group(1)))

    schema_fields: list[dict] = []
    sm = RE_SCHEMA.search(text)
    if sm:
        schema_fields = _schema_fields(sm.group(1))
    for m in RE_MODEL.finditer(text):
        out["models"].append({
            "file": rel, "lineno": _lineno(text, m.start()),
            "orm": "mongoose", "name": m.group(1), "table": m.group(1).lower(),
            "fields": schema_fields, "relationships": [],
        })
    for m in RE_DEFINE.finditer(text):
        out["models"].append({
            "file": rel, "lineno": _lineno(text, m.start()),
            "orm": "sequelize", "name": m.group(1), "table": m.group(1).lower(),
            "fields": _schema_fields(m.group(2)), "relationships": [],
        })
    return out


def _package(source: str) -> str:
    parts = source.split("/")
    if source.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def _schema_fields(body: str) -> list[dict]:
    fields: list[dict] = []
    seen: set[str] = set()
    for m in RE_FIELD_OBJ.finditer(body):
        name, inner = m.group(1), m.group(2)
        tm = re.search(r"type\s*:\s*(?:DataTypes\.)?(\w+)", inner)
        ftype = tm.group(1) if tm else ""
        nullable = False if re.search(r"required\s*:\s*true", inner) else None
        constraints = []
        if re.search(r"unique\s*:\s*true", inner):
            constraints.append("unique")
        dm = re.search(r"default\s*:\s*([^,}]+)", inner)
        default = dm.group(1).strip() if dm else None
        fields.append({"name": name, "type": ftype, "nullable": nullable,
                       "primary_key": False, "default": default, "constraints": constraints})
        seen.add(name)
    for m in RE_FIELD_SHORT.finditer(RE_FIELD_OBJ.sub("", body)):
        if m.group(1) not in seen:
            fields.append({"name": m.group(1), "type": m.group(2), "nullable": None,
                           "primary_key": False, "default": None, "constraints": []})
    return fields