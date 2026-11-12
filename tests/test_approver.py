import pytest

from myagent import approver, facts, roles
from myagent.analyzer import analyze_repo
from myagent.llm import LLMError
from myagent.render.assemble import assemble_doc
from myagent.render.narrative import offline_narrative

from fakes import FakeLLM, verdict_json


def _doc(fixture_repo, role_id="API", mode="offline"):
    f = analyze_repo(fixture_repo("fastapi_app"))
    role = roles.get_role(role_id)
    if mode == "offline":
        narratives = {s.id: offline_narrative(s, f, role)
                      for s in role.sections if s.kind == "narrative"}
    else:
        narratives = {s.id: "Detailed narrative grounded in the facts. " * 15
                      for s in role.sections if s.kind == "narrative"}
    md = assemble_doc(role, f, narratives, mode, facts.facts_sha256(f), ["main.py"])
    return role, f, md


def _checks(role, md, f, mode="offline"):
    return approver.deterministic_checks(role, md, f, mode)


def test_clean_offline_doc_passes(fixture_repo):
    role, f, md = _doc(fixture_repo)
    v = approver.review(role, md, f, "offline")
    assert v.approved
    assert v.stage == "deterministic"


def test_d01_missing_section(fixture_repo):
    role, f, md = _doc(fixture_repo)
    md = md.replace("## Endpoints", "## Something else")
    issues = _checks(role, md, f)
    assert any(i.check == "D01" and i.severity == "blocker" for i in issues)


def test_d01_short_narrative_online(fixture_repo):
    role, f, md = _doc(fixture_repo, mode="llm")
    md = md.replace("Detailed narrative grounded in the facts. " * 15, "short")
    issues = _checks(role, md, f, mode="llm")
    assert any(i.check == "D01" and i.severity == "major" for i in issues)


def test_d02_nonexistent_citation(fixture_repo):
    role, f, md = _doc(fixture_repo)
    md += "\nSee `ghost/file.py` for details.\n"
    issues = _checks(role, md, f)
    assert any(i.check == "D02" for i in issues)


def test_d02_existing_and_proposed_ok(fixture_repo):
    role, f, md = _doc(fixture_repo)
    md += "\nSee `main.py`. Create `new_module.py` to extend.\n"
    issues = _checks(role, md, f)
    assert not any(i.check == "D02" for i in issues)


def test_d03_missing_route(fixture_repo):
    role, f, md = _doc(fixture_repo)
    md = md.replace("| GET | `/users/me` |", "| GET | `/users/me2` |")
    issues = _checks(role, md, f)
    assert any(i.check == "D03" and i.severity == "blocker" for i in issues)


def test_d03_extra_route(fixture_repo):
    role, f, md = _doc(fixture_repo)
    md = md.replace("## Sources", "| GET | `/ghost` | x | y | — | — |\n\n## Sources")
    issues = _checks(role, md, f)
    assert any(i.check == "D03" for i in issues)


def test_d03_param_normalization(fixture_repo):
    role, f, md = _doc(fixture_repo)
    md = md.replace("{item_id}", ":id")
    issues = _checks(role, md, f)
    assert not any(i.check == "D03" for i in issues)


def test_d04_missing_model(fixture_repo):
    role, f, md = _doc(fixture_repo, role_id="DATABASE")
    md = md.replace("Item", "Thing")
    issues = _checks(role, md, f)
    assert any(i.check == "D04" for i in issues)


def test_d05_secret(fixture_repo):
    role, f, md = _doc(fixture_repo)
    md += "\nkey sk-abcdefghijklmnopqrstuvwx\n"
    issues = _checks(role, md, f)
    assert any(i.check == "D05" and i.severity == "blocker" for i in issues)


def test_d07_sentinel_in_llm_mode(fixture_repo):
    role, f, md = _doc(fixture_repo, mode="offline")
    issues = _checks(role, md, f, mode="llm")
    assert any(i.check == "D07" for i in issues)


def test_d08_tampered_facts_section(fixture_repo):
    role, f, md = _doc(fixture_repo)
    md = md.replace("| GET | `/items` |", "| GET | `/items9` |", 1)
    issues = _checks(role, md, f)
    assert any(i.check == "D08" for i in issues)


def test_parse_verdict_clean():
    v = approver.parse_verdict(verdict_json(True))
    assert v.approved


def test_parse_verdict_fenced():
    v = approver.parse_verdict("```json\n" + verdict_json(True) + "\n```")
    assert v.approved


def test_parse_verdict_prose_wrapped():
    v = approver.parse_verdict("Here is my review:\n" + verdict_json(False) + "\nThanks")
    assert not v.approved


def test_parse_verdict_garbage():
    with pytest.raises(ValueError):
        approver.parse_verdict("no json here")


def test_llm_review_failure_degrades(fixture_repo):
    role, f, md = _doc(fixture_repo, mode="llm")
    llm = FakeLLM(lambda s, u, j: LLMError("review down"))
    v = approver.review(role, md, f, "llm", llm=llm)
    assert v.stage == "deterministic-only"
    assert v.approved


def test_llm_review_disapprove(fixture_repo):
    role, f, md = _doc(fixture_repo, mode="llm")
    issue = {"severity": "major", "section": "endpoints", "message": "wrong"}
    llm = FakeLLM(lambda s, u, j: verdict_json(False, [issue]))
    v = approver.review(role, md, f, "llm", llm=llm)
    assert not v.approved
    assert v.stage == "both"


def test_offline_review_makes_no_llm_calls(fixture_repo):
    role, f, md = _doc(fixture_repo)
    llm = FakeLLM(lambda s, u, j: verdict_json(True))
    approver.review(role, md, f, "offline", llm=llm)
    assert llm.calls == []