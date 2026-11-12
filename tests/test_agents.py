from pathlib import Path

from myagent import facts, roles
from myagent.agents import Worker, run_doc
from myagent.analyzer import analyze_repo
from myagent.llm import ContextOverflowError, LLMError, NullLLM
from myagent.render.narrative import SENTINEL
from myagent.types import Config

from fakes import FakeLLM, markers_response, verdict_json


def cfg(**kw):
    base = dict(target=Path("."), provider="openai", model="m", api_key="k",
                max_rounds=2, context_tokens=16000, max_output_tokens=4000)
    base.update(kw)
    return Config(**base)


def test_draft_online(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role("API")
    llm = FakeLLM(lambda s, u, j: markers_response(role))
    worker = Worker(role, llm, cfg())
    md, narratives, sources, degraded = worker.draft(f, "")
    assert not degraded
    assert "Detailed narrative content" in md
    assert "| GET | `/items`" in md
    assert "main.py" in sources
    assert SENTINEL not in md
    assert len(llm.calls) == 1


def test_draft_missing_markers_retries_then_falls_back(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role("API")
    llm = FakeLLM(lambda s, u, j: "no markers at all")
    worker = Worker(role, llm, cfg())
    md, narratives, sources, degraded = worker.draft(f, "")
    assert degraded
    assert len(llm.calls) == 2
    assert SENTINEL in md


def test_draft_partial_markers_fills_missing(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role("API")
    first = next(s.id for s in role.sections if s.kind == "narrative")
    llm = FakeLLM(lambda s, u, j: f"===SECTION: {first}===\nOnly one section.")
    worker = Worker(role, llm, cfg())
    md, narratives, sources, degraded = worker.draft(f, "")
    assert "Only one section." in md
    assert degraded
    assert SENTINEL in md


def test_draft_llm_error_degrades_to_offline(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role("API")
    llm = FakeLLM(lambda s, u, j: LLMError("boom"))
    worker = Worker(role, llm, cfg())
    md, narratives, sources, degraded = worker.draft(f, "")
    assert degraded
    assert SENTINEL in md
    assert "| GET | `/items`" in md


def test_draft_context_overflow_halves_budget(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role("API")
    state = {"n": 0}

    def responder(s, u, j):
        state["n"] += 1
        if state["n"] == 1:
            return ContextOverflowError("context length exceeded")
        return markers_response(role)

    llm = FakeLLM(responder)
    worker = Worker(role, llm, cfg())
    md, narratives, sources, degraded = worker.draft(f, "")
    assert not degraded
    assert state["n"] == 2


def test_revision_prompt_contains_issues(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role("API")
    llm = FakeLLM(lambda s, u, j: markers_response(role))
    worker = Worker(role, llm, cfg())
    from myagent.types import Issue
    issues = [Issue("D03", "blocker", "endpoints", "missing route GET /x")]
    md, _, _, _ = worker.draft(f, "", attempt=1, previous="PREVIOUS TEXT", issues=issues)
    system, user, _ = llm.calls[0]
    assert "missing route GET /x" in user
    assert "PREVIOUS TEXT" in user


def test_run_doc_offline_no_llm_calls(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role("API")
    llm = FakeLLM(lambda s, u, j: markers_response(role))
    result = run_doc(role, f, "", llm, cfg(offline=True))
    assert result.status == "written"
    assert result.mode == "offline"
    assert result.verdict.approved
    assert llm.calls == []


def test_run_doc_online_approved(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role("API")

    def responder(s, u, j):
        return verdict_json(True) if j else markers_response(role)

    llm = FakeLLM(responder)
    result = run_doc(role, f, "", llm, cfg())
    assert result.verdict.approved
    assert result.mode == "llm"
    assert result.rounds_used == 0


def test_run_doc_revision_loop_terminates_flagged(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role("API")
    issue = {"severity": "major", "section": "endpoints",
             "message": "invented endpoint", "suggestion": "remove it"}

    def responder(s, u, j):
        return verdict_json(False, [issue]) if j else markers_response(role)

    llm = FakeLLM(responder)
    result = run_doc(role, f, "", llm, cfg(max_rounds=2))
    assert not result.verdict.approved
    assert result.rounds_used == 2
    assert "## Review notes" in result.markdown
    assert "invented endpoint" in result.markdown


def test_run_doc_llm_failure_degrades_cleanly(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role("API")
    llm = FakeLLM(lambda s, u, j: LLMError("HTTP 401"))
    result = run_doc(role, f, "", llm, cfg())
    assert result.degraded
    assert result.mode == "offline"
    assert result.verdict.approved
    assert result.rounds_used == 0
    assert "## Review notes" not in result.markdown