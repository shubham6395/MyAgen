from __future__ import annotations

import os
import re
from pathlib import Path

from myagent import util

MAX_FILES = 20000
MAX_PARSE_BYTES = 1_000_000

ALWAYS_SKIP = {".git", ".myagent"}

DEFAULT_IGNORES = """
node_modules/
__pycache__/
.venv/
venv/
dist/
build/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.idea/
*.egg-info/
.DS_Store
"""

LANGUAGES = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".go": "Go", ".rb": "Ruby", ".java": "Java", ".rs": "Rust", ".php": "PHP",
    ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++", ".cc": "C++", ".cs": "C#",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell", ".bat": "Batch",
    ".sql": "SQL", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".json": "JSON", ".toml": "TOML", ".yaml": "YAML", ".yml": "YAML", ".ini": "INI",
    ".md": "Markdown", ".rst": "reStructuredText", ".txt": "Text",
    ".vue": "Vue", ".svelte": "Svelte", ".kt": "Kotlin", ".swift": "Swift",
    ".dart": "Dart", ".ex": "Elixir", ".exs": "Elixir", ".hs": "Haskell",
    ".lua": "Lua", ".r": "R", ".scala": "Scala", ".zig": "Zig",
}

SPECIAL_NAMES = {"makefile": "Makefile", "gemfile": "Ruby", "rakefile": "Ruby"}

TEST_GLOBS = (
    "**/test_*.py", "**/*_test.py", "**/tests/**", "**/test/**",
    "**/*.test.*", "**/*.spec.*", "**/__tests__/**", "**/*_test.go",
)
MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt", "cargo.toml",
    "go.mod", "gemfile", "composer.json", "pipfile", "setup.py", "setup.cfg",
}
CONFIG_EXTS = {"JSON", "TOML", "YAML", "INI"}
DOC_LANGS = {"Markdown", "reStructuredText", "Text"}
SCRIPT_LANGS = {"Shell", "PowerShell", "Batch", "Makefile", "Dockerfile"}
ASSET_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".mp4", ".pdf", ".webp", ".eot",
}


def detect_language(filename: str) -> str:
    lower = filename.lower()
    if lower in SPECIAL_NAMES:
        return SPECIAL_NAMES[lower]
    if lower.startswith("dockerfile"):
        return "Dockerfile"
    return LANGUAGES.get(Path(lower).suffix, "Other")


def role_hint(rel: str, language: str) -> str:
    name = rel.rsplit("/", 1)[-1].lower()
    if any(util.glob_match(p, rel) for p in TEST_GLOBS):
        return "test"
    if name in MANIFEST_NAMES or (name.startswith("requirements") and name.endswith(".txt")):
        return "config"
    if language in DOC_LANGS:
        return "docs"
    if language in SCRIPT_LANGS:
        return "script"
    if language in CONFIG_EXTS or name.startswith(".env") or name in {".gitignore", ".editorconfig"}:
        return "config"
    if Path(name).suffix in ASSET_EXTS:
        return "asset"
    if language != "Other":
        return "source"
    return "other"


class _Rule:
    __slots__ = ("regex", "negated", "dir_only")

    def __init__(self, regex: re.Pattern, negated: bool, dir_only: bool):
        self.regex = regex
        self.negated = negated
        self.dir_only = dir_only


def _compile_rule(line: str) -> _Rule | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    negated = line.startswith("!")
    if negated:
        line = line[1:]
    dir_only = line.endswith("/")
    if dir_only:
        line = line[:-1]
    anchored = line.startswith("/")
    if anchored:
        line = line[1:]
    if "/" in line:
        anchored = True
    body = util.glob_regex(line).pattern[1:-1]
    if not anchored:
        body = "(?:.*/)?" + body
    return _Rule(re.compile("^" + body + "$"), negated, dir_only)


class Gitignore:
    """Last-match-wins gitignore semantics scoped to its directory."""

    def __init__(self, base: str, text: str):
        self.base = base
        self.rules = [r for line in text.splitlines() if (r := _compile_rule(line))]

    def decision(self, rel: str, is_dir: bool) -> bool | None:
        if self.base:
            if not rel.startswith(self.base + "/"):
                return None
            local = rel[len(self.base) + 1:]
        else:
            local = rel
        result = None
        parts = local.split("/")
        ancestors = parts if is_dir else parts[:-1]
        for rule in self.rules:
            if rule.dir_only:
                hit = any(
                    rule.regex.match("/".join(ancestors[:i + 1]))
                    for i in range(len(ancestors))
                )
            else:
                hit = bool(rule.regex.match(local))
            if hit:
                result = not rule.negated
        return result


def walk_repo(root: Path, extra_skip: set[str] | None = None) -> dict:
    root = Path(root).resolve()
    extra_skip = extra_skip or set()
    engines: list[Gitignore] = [Gitignore("", DEFAULT_IGNORES)]
    files: list[dict] = []
    texts: dict[str, str] = {}
    cap_hit = False

    def ignored(rel: str, is_dir: bool) -> bool:
        if rel.rsplit("/", 1)[-1] in ALWAYS_SKIP:
            return True
        if rel in extra_skip or any(rel.startswith(s + "/") for s in extra_skip):
            return True
        decision = None
        for eng in engines:
            d = eng.decision(rel, is_dir)
            if d is not None:
                decision = d
        return bool(decision)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = util.posix_rel(Path(dirpath), root)
        if rel_dir == ".":
            rel_dir = ""
        gi = Path(dirpath) / ".gitignore"
        if gi.is_file():
            text = util.read_text_safe(gi)
            if text is not None:
                engines.append(Gitignore(rel_dir, text))
        dirnames[:] = [
            d for d in sorted(dirnames)
            if not ignored(f"{rel_dir}/{d}" if rel_dir else d, True)
        ]
        for fn in sorted(filenames):
            rel = f"{rel_dir}/{fn}" if rel_dir else fn
            if ignored(rel, False):
                continue
            if len(files) >= MAX_FILES:
                cap_hit = True
                break
            p = Path(dirpath) / fn
            try:
                size = p.stat().st_size
                sha = util.sha256_file(p)
            except OSError:
                continue
            lang = detect_language(fn)
            text = util.read_text_safe(p) if size <= MAX_PARSE_BYTES else None
            files.append({
                "path": rel, "sha256": sha, "bytes": size,
                "loc": len(text.splitlines()) if text is not None else 0,
                "language": lang, "role_hint": role_hint(rel, lang),
            })
            if text is not None:
                texts[rel] = text
        if cap_hit:
            break
    return {"files": files, "texts": texts,
            "truncation": {"cap_hit": cap_hit, "omitted": {}}}