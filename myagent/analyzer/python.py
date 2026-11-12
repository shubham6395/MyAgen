from __future__ import annotations

import ast
import re

from myagent import util

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}
_BUILTIN_TYPES = {"int", "str", "float", "bool", "bytes", "list", "dict", "Session", "Any"}


def extract(rel: str, text: str, module_map: dict[str, str] | None = None) -> dict:
    tree = ast.parse(text)
    module_map = module_map or {}
    out = {"symbols": [], "imports": [], "routes": [], "models": [], "mounts": []}
    framework = _framework(tree)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out["imports"].extend(_imports(rel, node, module_map))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out["symbols"].append(_function_symbol(rel, node, node.name, "function"))
            route = _route(rel, node, framework, node.name)
            if route:
                out["routes"].append(route)
        elif isinstance(node, ast.ClassDef):
            out["symbols"].append(_class_symbol(rel, node))
            model = _model(rel, node)
            if model:
                out["models"].append(model)
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out["symbols"].append(
                        _function_symbol(rel, sub, f"{node.name}.{sub.name}", "method")
                    )
    return out


def _framework(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in ("fastapi", "flask", "django"):
                return top
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in ("fastapi", "flask", "django"):
                    return top
    return "generic"


def _resolve_relative(rel: str, level: int, module: str | None) -> str:
    parts = rel.split("/")[:-1]
    up = level - 1
    if up > len(parts):
        return ""
    base_parts = parts[:len(parts) - up] if up else parts
    base = ".".join(base_parts)
    if module:
        return f"{base}.{module}" if base else module
    return base


def _imports(rel: str, node, module_map: dict[str, str]) -> list[dict]:
    records = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            target = module_map.get(alias.name)
            records.append({
                "from_file": rel,
                "target": target or alias.name.split(".")[0],
                "kind": "internal" if target else "external",
                "names": [alias.asname or alias.name],
            })
    else:
        module = node.module
        if node.level:
            module = _resolve_relative(rel, node.level, module)
        target = module_map.get(module or "")
        records.append({
            "from_file": rel,
            "target": target or (module or "").split(".")[0],
            "kind": "internal" if target else "external",
            "names": [a.name for a in node.names],
        })
    return records


def _signature(node) -> str:
    args = node.args
    parts: list[str] = []
    pos = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(pos) - len(args.defaults)) + list(args.defaults)
    for a, d in zip(pos, defaults):
        s = a.arg
        if a.annotation is not None:
            s += ": " + ast.unparse(a.annotation)
        if d is not None:
            s += "=" + ast.unparse(d)
        parts.append(s)
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        parts.append("*")
    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        s = a.arg
        if a.annotation is not None:
            s += ": " + ast.unparse(a.annotation)
        if d is not None:
            s += "=" + ast.unparse(d)
        parts.append(s)
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    sig = "(" + ", ".join(parts) + ")"
    if node.returns is not None:
        sig += " -> " + ast.unparse(node.returns)
    return sig


def _base_symbol(rel: str, node, kind: str, qualname: str) -> dict:
    return {
        "file": rel, "lineno": node.lineno,
        "end_lineno": getattr(node, "end_lineno", node.lineno),
        "kind": kind, "name": node.name, "qualname": qualname,
        "signature": "", "docstring": util.truncate(ast.get_docstring(node) or "", 300),
        "decorators": [ast.unparse(d) for d in node.decorator_list],
        "bases": [], "exported": not node.name.startswith("_"),
    }


def _function_symbol(rel: str, node, qualname: str, kind: str) -> dict:
    rec = _base_symbol(rel, node, kind, qualname)
    rec["signature"] = _signature(node)
    return rec


def _class_symbol(rel: str, node: ast.ClassDef) -> dict:
    rec = _base_symbol(rel, node, "class", node.name)
    rec["bases"] = [ast.unparse(b) for b in node.bases]
    return rec


def _route(rel: str, node, framework: str, qualname: str) -> dict | None:
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            continue
        attr = dec.func.attr
        if attr in HTTP_METHODS:
            methods = [attr.upper()]
        elif attr == "route":
            methods = ["GET"]
            for kw in dec.keywords:
                if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    methods = [
                        e.value.upper() for e in kw.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    ]
        else:
            continue
        if not dec.args or not isinstance(dec.args[0], ast.Constant):
            continue
        path = dec.args[0].value
        if not isinstance(path, str):
            continue
        auth_hints: list[str] = []
        response_model = None
        for kw in dec.keywords:
            if kw.arg == "dependencies":
                auth_hints.append("dependencies:" + util.truncate(ast.unparse(kw.value), 80))
            elif kw.arg == "response_model":
                response_model = ast.unparse(kw.value)
        pos = list(node.args.posonlyargs) + list(node.args.args)
        defaults = [None] * (len(pos) - len(node.args.defaults)) + list(node.args.defaults)
        for a, d in zip(pos, defaults):
            if d is not None and "Depends(" in ast.unparse(d):
                dep = ast.unparse(d)
                if re.search(r"auth|user|token|current|login|permission|security", dep, re.I):
                    auth_hints.append("depends:" + util.truncate(dep, 80))
        request_model = None
        for a, d in zip(pos, defaults):
            if a.annotation is not None and d is None:
                ann = ast.unparse(a.annotation)
                if ann not in _BUILTIN_TYPES and "." not in ann:
                    request_model = ann
                    break
        return {
            "file": rel, "lineno": node.lineno, "framework": framework,
            "method": methods[0] if methods else "GET", "path": path,
            "handler": qualname, "auth_hints": auth_hints,
            "request_model": request_model, "response_model": response_model,
        }
    return None


def _model(rel: str, node: ast.ClassDef) -> dict | None:
    bases = [ast.unparse(b) for b in node.bases]
    is_sa = any(b == "Base" or b.endswith(".Base") for b in bases)
    is_dj = any(b in ("models.Model", "Model") or b.endswith(".Model") for b in bases)
    if not (is_sa or is_dj):
        return None
    table = None
    fields: list[dict] = []
    relationships: list[dict] = []
    for sub in node.body:
        if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Constant):
            names = [t.id for t in sub.targets if isinstance(t, ast.Name)]
            if "__tablename__" in names:
                table = sub.value.value
        call = None
        name = None
        if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call):
            call = sub.value
            names = [t.id for t in sub.targets if isinstance(t, ast.Name)]
            name = names[0] if names else None
        elif isinstance(sub, ast.AnnAssign) and isinstance(sub.value, ast.Call):
            call = sub.value
            name = sub.target.id if isinstance(sub.target, ast.Name) else None
        if call is None or name is None:
            continue
        fname = ast.unparse(call.func)
        if fname.endswith("relationship"):
            target = ""
            if call.args and isinstance(call.args[0], ast.Constant):
                target = call.args[0].value
            relationships.append({"kind": "one-to-many", "target": target})
        elif fname in ("Column", "mapped_column") or fname.endswith((".Column", ".mapped_column")) or (is_dj and fname.startswith("models.")):
            fields.append(_field(name, call, is_dj))
    return {
        "file": rel, "lineno": node.lineno,
        "orm": "sqlalchemy" if is_sa else "django",
        "name": node.name, "table": table or node.name.lower(),
        "fields": fields, "relationships": relationships,
    }


def _field(name: str, call: ast.Call, is_dj: bool) -> dict:
    ftype = ""
    constraints: list[str] = []
    nullable = None
    pk = False
    default = None
    if is_dj:
        ftype = ast.unparse(call.func).split(".")[-1]
    elif call.args:
        ftype = ast.unparse(call.args[0])
    for a in call.args[1:]:
        u = ast.unparse(a)
        if u.startswith("ForeignKey("):
            constraints.append(u)
    for kw in call.keywords:
        val = kw.value
        if kw.arg == "primary_key":
            pk = bool(val.value) if isinstance(val, ast.Constant) else True
        elif kw.arg == "nullable":
            nullable = bool(val.value) if isinstance(val, ast.Constant) else None
        elif kw.arg == "unique" and isinstance(val, ast.Constant) and val.value:
            constraints.append("unique")
        elif kw.arg == "index" and isinstance(val, ast.Constant) and val.value:
            constraints.append("index")
        elif kw.arg == "default":
            default = util.truncate(ast.unparse(val), 60)
        elif kw.arg == "max_length":
            constraints.append(f"max_length={ast.unparse(val)}")
        elif kw.arg in ("required",) and isinstance(val, ast.Constant):
            nullable = not bool(val.value)
    return {"name": name, "type": ftype, "nullable": nullable,
            "primary_key": pk, "default": default, "constraints": constraints}