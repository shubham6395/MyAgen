from __future__ import annotations

import json
import logging
import re

from myagent import prompts, roles, util
from myagent.llm import LLMError, NullLLM
from myagent.render import render_section
from myagent.render.narrative import SENTINEL
from myagent.types import Issue, Role, Verdict

log = logging.getLogger("myagent.approver")

SUITE_FILENAMES = {r.filename for r in roles.ROLES}
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_ROUTE_ROW = re.compile(r"^\|\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\|\s*`([^`]+)`", re.M)
_MODEL_HEADING = re.compile(r"^### (\w+) \(`", re.M)
_BACKTICK = re.compile(r"`([^`\n]+)`")
_FENCE = re.compile(r"```[\s\S]*?(?:```|$)")
_PATHLIKE = re.compile(r"^[\w./-]+\.\w{1,5}$")
_PROPOSED = re.compile(r"\b(create|new|proposed|add|would|should)\b", re.I)


def _norm_route(method: str, path: str) -> tuple[str, str]:
    path = re.sub(r"\{[^}]*\}|:[\w]+", "{}", path)
    if len(path) > 1:
        path = path.rstrip("/")
    return method.lower(), path


def _section_body(md: str, title: str) -> str | None:
    header = f"## {title}"
    idx = md.find(header)
    if idx == -1:
        return None
    rest = md[idx + len(header):]
    nxt = rest.find("\n## ")
    return rest[:nxt] if nxt != -1 else rest


def deterministic_checks(role: Role, md: str, facts: dict, mode: str) -> list[Issue]:
    issues: list[Issue] = []
    offline = mode == "offline"

    for sec in role.sections:
        body = _section_body(md, sec.title)
        if body is None:
            issues.append(Issue("D01", "blocker", sec.id, f"missing section: {sec.title}"))
            continue
        if sec.kind == "narrative" and not sec.optional:
            placeholder = offline and SENTINEL in body
            not_applicable = "not detected" in body.lower() or "not applicable" in body.lower()
            if not placeholder and not not_applicable and len(body.strip()) < sec.min_chars:
                issues.append(Issue("D01", "major", sec.id,
                                    f"narrative too short ({len(body.strip())} < {sec.min_chars} chars)"))

    file_set = {f["path"] for f in facts["files"]}
    prose = _FENCE.sub("", md)
    cited = 0
    for line in prose.splitlines():
        if _PROPOSED.search(line):
            continue
        for m in _BACKTICK.finditer(line):
            token = m.group(1).strip()
            token = re.sub(r":\d+$", "", token)
            if not token or " " in token or token.startswith("/") or ":" in token:
                continue
            if token in SUITE_FILENAMES:
                continue
            if not (_PATHLIKE.match(token) or "/" in token):
                continue
            if token not in file_set:
                cited += 1
                if cited <= 10:
                    issues.append(Issue("D02", "major", None,
                                        f"cited path not in repo: {token}",
                                        "cite only files present in the facts"))

    if role.id in ("API", "BLUEPRINT"):
        fact_routes = {_norm_route(r["method"], r["path"]) for r in facts["routes"]}
        doc_routes = {_norm_route(m.group(1), m.group(2)) for m in _ROUTE_ROW.finditer(md)}
        for method, path in sorted(fact_routes - doc_routes):
            issues.append(Issue("D03", "blocker", "endpoints",
                                f"route missing from doc: {method.upper()} {path}"))
        for method, path in sorted(doc_routes - fact_routes):
            issues.append(Issue("D03", "blocker", "endpoints",
                                f"route in doc not in facts: {method.upper()} {path}"))

    if role.id in ("DATABASE", "BLUEPRINT"):
        model_names = {m["name"] for m in facts["models"]}
        for name in sorted(model_names):
            if not re.search(rf"\b{re.escape(name)}\b", md):
                issues.append(Issue("D04", "major", "models", f"model missing from doc: {name}"))
        for m in _MODEL_HEADING.finditer(md):
            if m.group(1) not in model_names:
                issues.append(Issue("D04", "major", "models",
                                    f"model in doc not in facts: {m.group(1)}"))

    for pat in _SECRET_PATTERNS:
        if pat.search(md):
            issues.append(Issue("D05", "blocker", None, "secret-shaped string in document"))
            break

    for m in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", md):
        target = m.group(1).split("#")[0]
        if target.endswith(".md") and target in SUITE_FILENAMES:
            continue
        if target.endswith(".md") and "/" not in target and target not in file_set:
            issues.append(Issue("D06", "minor", None, f"unresolved doc link: {target}"))

    if not offline and SENTINEL in md:
        issues.append(Issue("D07", "blocker", None, "offline placeholder leaked into LLM-mode doc"))

    for sec in role.sections:
        if sec.kind == "facts":
            expected = render_section(sec, facts, role)
            if expected not in md:
                issues.append(Issue("D08", "blocker", sec.id,
                                    f"facts section drifted from renderer: {sec.title}"))
    return issues


def parse_verdict(text: str) -> Verdict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    decoder = json.JSONDecoder()
    obj = None
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[m.start():])
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(obj, dict) or "approved" not in obj:
        raise ValueError("no valid verdict JSON found")
    issues = []
    for it in obj.get("issues", []):
        if isinstance(it, dict) and it.get("message"):
            sev = it.get("severity", "minor")
            if sev not in ("blocker", "major", "minor"):
                sev = "minor"
            issues.append(Issue("llm", sev, it.get("section"),
                                str(it["message"]), str(it.get("suggestion", ""))))
    scores = obj.get("scores") if isinstance(obj.get("scores"), dict) else None
    return Verdict(approved=bool(obj["approved"]), issues=issues, scores=scores,
                   summary=str(obj.get("summary", "")), stage="llm")


def _llm_review(role: Role, md: str, facts: dict, llm, shared_context: str) -> Verdict:
    subset, _ = roles.build_context(role, facts, budget_tokens=8000)
    user = prompts.approver_prompt(role, md, subset, shared_context)
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            text = llm.complete("You are the approver agent. Return only the JSON verdict.",
                                user, json_mode=True)
            return parse_verdict(text)
        except ValueError as e:
            last_err = e
            user = "Return ONLY the JSON verdict object, no prose.\n\n" + user
        except LLMError:
            raise
    raise LLMError(f"verdict parse failed: {last_err}")


def review(role: Role, md: str, facts: dict, mode: str, llm=None,
           shared_context: str = "") -> Verdict:
    issues = deterministic_checks(role, md, facts, mode)
    hard_fail = any(i.severity in ("blocker", "major") for i in issues)
    if mode == "offline" or llm is None or isinstance(llm, NullLLM):
        return Verdict(approved=not hard_fail, issues=issues, stage="deterministic")
    try:
        llm_verdict = _llm_review(role, md, facts, llm, shared_context)
    except LLMError as e:
        log.warning("LLM review unavailable for %s: %s", role.filename, e)
        issues.append(Issue("llm-review", "minor", None, "llm review unavailable"))
        return Verdict(approved=not hard_fail, issues=issues, stage="deterministic-only")
    llm_hard = any(i.severity in ("blocker", "major") for i in llm_verdict.issues)
    approved = not hard_fail and llm_verdict.approved and not llm_hard
    return Verdict(approved=approved, issues=issues + llm_verdict.issues,
                   scores=llm_verdict.scores, summary=llm_verdict.summary, stage="both")