from __future__ import annotations

import posixpath
from pathlib import Path

from myagent import facts, util
from myagent.analyzer import detect, generic, javascript, python, walker

_JS_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


def analyze_repo(target: Path, out_dir: Path | None = None) -> dict:
    target = Path(target).resolve()
    extra: set[str] = set()
    if out_dir is not None:
        try:
            extra.add(util.posix_rel(Path(out_dir).resolve(), target))
        except ValueError:
            pass
    walk = walker.walk_repo(target, extra_skip=extra)
    f = facts.new_facts()
    f["files"] = walk["files"]
    f["truncation"] = walk["truncation"]
    f["repo"] = _repo_summary(target, walk["files"])
    texts = walk["texts"]
    module_map = _python_module_map(walk["files"])
    file_set = {rec["path"] for rec in walk["files"]}
    mounts: list[dict] = []
    for rec in walk["files"]:
        rel, lang = rec["path"], rec["language"]
        text = texts.get(rel)
        if text is None:
            continue
        if rec["role_hint"] not in ("source", "script", "test") and lang not in ("Python", "JavaScript", "TypeScript"):
            continue
        try:
            if lang == "Python":
                out = python.extract(rel, text, module_map)
            elif lang in ("JavaScript", "TypeScript"):
                out = javascript.extract(rel, text)
            else:
                out = generic.extract(rel, text, lang)
        except SyntaxError as e:
            f["parse_errors"].append({"file": rel, "error": str(e)})
            out = generic.extract(rel, text, lang)
        except Exception as e:
            f["parse_errors"].append({"file": rel, "error": str(e)})
            continue
        f["symbols"].extend(out["symbols"])
        f["imports"].extend(out["imports"])
        f["routes"].extend(out["routes"])
        f["models"].extend(out["models"])
        mounts.extend(out.get("mounts", []))
    _resolve_js_imports(f["imports"], file_set)
    _apply_mounts(f["routes"], mounts, file_set)
    detect.run(f, texts, target)
    facts.validate_facts(f)
    return f


def _repo_summary(target: Path, files: list[dict]) -> dict:
    by_lang: dict[str, dict] = {}
    total = 0
    for rec in files:
        lang = rec["language"]
        agg = by_lang.setdefault(lang, {"lang": lang, "files": 0, "bytes": 0})
        agg["files"] += 1
        agg["bytes"] += rec["bytes"]
        total += rec["bytes"]
    languages = sorted(by_lang.values(), key=lambda x: -x["bytes"])
    for agg in languages:
        agg["pct"] = round(100 * agg["bytes"] / total, 1) if total else 0.0
    return {
        "root": str(target), "name": target.name,
        "file_count": len(files), "total_bytes": total,
        "languages": languages,
        "primary_language": languages[0]["lang"] if languages else "",
    }


def _python_module_map(files: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for rec in files:
        rel = rec["path"]
        if not rel.endswith(".py"):
            continue
        dotted = rel[:-3].replace("/", ".")
        if dotted.endswith(".__init__"):
            mapping[dotted[:-9]] = rel
        else:
            mapping[dotted] = rel
    return mapping


def _resolve_js_target(from_file: str, source: str, file_set: set[str]) -> str | None:
    base = posixpath.normpath(posixpath.join(posixpath.dirname(from_file), source))
    candidates = [base] + [base + ext for ext in _JS_EXTS] + [
        posixpath.join(base, "index" + ext) for ext in _JS_EXTS
    ]
    for cand in candidates:
        if cand in file_set:
            return cand
    return None


def _resolve_js_imports(imports: list[dict], file_set: set[str]) -> None:
    for imp in imports:
        if imp["kind"] == "internal" and imp["target"].startswith("."):
            resolved = _resolve_js_target(imp["from_file"], imp["target"], file_set)
            if resolved:
                imp["target"] = resolved


def _apply_mounts(routes: list[dict], mounts: list[dict], file_set: set[str]) -> None:
    for mount in mounts:
        if not mount.get("source"):
            continue
        target = _resolve_js_target(mount["file"], mount["source"], file_set)
        if not target:
            continue
        prefix = mount["prefix"].rstrip("/")
        for route in routes:
            if route["file"] == target:
                joined = prefix + "/" + route["path"].lstrip("/")
                route["path"] = joined.rstrip("/") or "/"