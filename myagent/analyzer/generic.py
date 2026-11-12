from __future__ import annotations

import re

from myagent import util

_SYMBOL_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "Go": [
        (r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(", "function"),
        (r"\btype\s+([A-Za-z_]\w*)\s+(?:struct|interface)", "class"),
    ],
    "Ruby": [
        (r"\bdef\s+(?:self\.)?([A-Za-z_]\w*[?!=]?)", "function"),
        (r"\bclass\s+([A-Za-z_]\w*)", "class"),
        (r"\bmodule\s+([A-Za-z_]\w*)", "class"),
    ],
    "Java": [
        (r"\b(?:class|interface|enum)\s+([A-Za-z_]\w*)", "class"),
        (r"\b(?:public|private|protected)\s+[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*\(", "method"),
    ],
    "C#": [
        (r"\b(?:class|interface|enum|record)\s+([A-Za-z_]\w*)", "class"),
    ],
    "Rust": [
        (r"\bfn\s+([A-Za-z_]\w*)\s*[<(]", "function"),
        (r"\b(?:struct|enum|trait)\s+([A-Za-z_]\w*)", "class"),
    ],
    "PHP": [
        (r"\bfunction\s+([A-Za-z_]\w*)\s*\(", "function"),
        (r"\bclass\s+([A-Za-z_]\w*)", "class"),
    ],
    "Kotlin": [
        (r"\bfun\s+([A-Za-z_]\w*)\s*\(", "function"),
        (r"\b(?:class|object|interface)\s+([A-Za-z_]\w*)", "class"),
    ],
    "Swift": [
        (r"\bfunc\s+([A-Za-z_]\w*)\s*\(", "function"),
        (r"\b(?:class|struct|protocol|enum)\s+([A-Za-z_]\w*)", "class"),
    ],
}

_FALLBACK_SYMBOLS = [
    (r"\b(?:func|function|def|sub|proc)\s+([A-Za-z_]\w*)", "function"),
    (r"\b(?:class|module|struct|trait|interface)\s+([A-Za-z_]\w*)", "class"),
]

_IMPORT_PATTERNS: dict[str, str] = {
    "Go": r'import\s+(?:\(\s*)?"([^"]+)"',
    "Ruby": r"require(?:_relative)?\s+[\"']([^\"']+)[\"']",
    "Java": r"import\s+([\w.]+);",
    "Rust": r"\buse\s+([\w:]+)",
    "C": r'#include\s+[<"]([^>"]+)[>"]',
    "C++": r'#include\s+[<"]([^>"]+)[>"]',
    "PHP": r"\buse\s+([\w\\]+);",
    "Kotlin": r"import\s+([\w.]+)",
    "Swift": r"import\s+([A-Za-z_]\w*)",
}


def _lineno(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def extract(rel: str, text: str, language: str) -> dict:
    out = {"symbols": [], "imports": [], "routes": [], "models": [], "mounts": []}
    patterns = _SYMBOL_PATTERNS.get(language, _FALLBACK_SYMBOLS)
    for pat, kind in patterns:
        for m in re.finditer(pat, text):
            name = m.group(1)
            out["symbols"].append({
                "file": rel, "lineno": _lineno(text, m.start()),
                "end_lineno": _lineno(text, m.end()),
                "kind": kind, "name": name, "qualname": name,
                "signature": "", "docstring": "", "decorators": [],
                "bases": [], "exported": not name.startswith("_"),
            })
    imp_pat = _IMPORT_PATTERNS.get(language)
    if imp_pat:
        for m in re.finditer(imp_pat, text):
            target = m.group(1)
            out["imports"].append({
                "from_file": rel, "target": target,
                "kind": "external", "names": [],
            })
    return out