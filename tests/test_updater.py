import json
from pathlib import Path

from myagent import facts, roles, updater
from myagent.analyzer import analyze_repo
from myagent.cli import run_pipeline
from myagent.types import Config

from fakes import FakeLLM, markers_response, verdict_json


def cfg(target, **kw):
    base = dict(target=target, offline=True)
    base.update(kw)
    return Config(**base)


def fake_llm():
    def responder(system, user, json_mode):
        if json_mode:
            return verdict_json(True)
        for r in roles.ROLES:
            if f"Document: {r.filename}" in system:
                return markers_response(r)
        return ""
    return FakeLLM(responder)


def test_full_run_offline_16_docs(fixture_repo):
    root = fixture_repo("express_app")
    report = run_pipeline(cfg(root))
    docs = sorted(p.name for p in (root / "docs").glob("*.md"))
    assert len(docs) == 16
    assert "BLUEPRINT.md" in docs
    assert report.exit_code == 0
    assert (root / ".myagent" / "manifest.json").is_file()
    assert (root / ".myagent" / "report.json").is_file()
    assert all(d.verdict.approved for d in report.docs)


def test_full_run_fake_llm(fixture_repo):
    root = fixture_repo("express_app")
    c = cfg(root, offline=False, provider="openai", model="m", api_key="k")
    report = run_pipeline(c, llm=fake_llm())
    assert len(report.docs) == 16
    assert report.exit_code == 0
    assert all(d.mode == "llm" for d in report.docs)


def test_second_run_skips_all(fixture_repo):
    root = fixture_repo("express_app")
    run_pipeline(cfg(root))
    mtimes = {p.name: p.stat().st_mtime_ns for p in (root / "docs").glob("*.md")}
    report = run_pipeline(cfg(root))
    assert report.affected == []
    assert len(report.up_to_date) == 16
    assert report.exit_code == 0
    mtimes2 = {p.name: p.stat().st_mtime_ns for p in (root / "docs").glob("*.md")}
    assert mtimes == mtimes2


def test_incremental_route_edit(fixture_repo):
    root = fixture_repo("express_app")
    run_pipeline(cfg(root))
    route_file = root / "src" / "routes" / "users.js"
    route_file.write_text(route_file.read_text(encoding="utf-8") + "\n// touched\n",
                          encoding="utf-8")
    report = run_pipeline(cfg(root))
    assert "API" in report.affected
    assert "BLUEPRINT" in report.affected
    assert "MCP" not in report.affected
    assert "SETUP" not in report.affected
    assert "TESTING_QA" not in report.affected
    assert "DEBUGGING" not in report.affected


def test_dry_run_writes_nothing(fixture_repo):
    root = fixture_repo("express_app")
    report = run_pipeline(cfg(root, dry_run=True))
    assert not (root / "docs").exists()
    assert not (root / ".myagent").exists()
    assert len(report.affected) == 16


def test_only_filter(fixture_repo):
    root = fixture_repo("express_app")
    report = run_pipeline(cfg(root, only=["API", "README.md"]))
    assert sorted(report.affected) == ["API", "README"]
    assert sorted(p.name for p in (root / "docs").glob("*.md")) == ["API.md", "README.md"]


def test_corrupt_manifest_forces_full(fixture_repo):
    root = fixture_repo("express_app")
    run_pipeline(cfg(root))
    (root / ".myagent" / "manifest.json").write_text("{not json", encoding="utf-8")
    report = run_pipeline(cfg(root))
    assert len(report.affected) == 16


def test_config_digest_change_forces_full(fixture_repo):
    root = fixture_repo("express_app")
    run_pipeline(cfg(root))
    report = run_pipeline(cfg(root, offline=False, provider="openai", model="m", api_key="k"),
                          llm=fake_llm())
    assert len(report.affected) == 16


def test_hand_edited_doc_regenerates(fixture_repo):
    root = fixture_repo("express_app")
    run_pipeline(cfg(root))
    api = root / "docs" / "API.md"
    api.write_text(api.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
    report = run_pipeline(cfg(root))
    assert "API" in report.affected
    assert "hand edit" not in api.read_text(encoding="utf-8")


def test_deleted_file_triggers_regeneration(fixture_repo):
    root = fixture_repo("express_app")
    run_pipeline(cfg(root))
    (root / "src" / "routes" / "users.js").unlink()
    report = run_pipeline(cfg(root))
    assert "API" in report.affected
    api_text = (root / "docs" / "API.md").read_text(encoding="utf-8")
    assert "/users/:id" not in api_text


def test_manifest_doc_version_increments(fixture_repo):
    root = fixture_repo("express_app")
    run_pipeline(cfg(root))
    m1 = json.loads((root / ".myagent" / "manifest.json").read_text(encoding="utf-8"))
    assert m1["docs"]["API.md"]["doc_version"] == 1
    run_pipeline(cfg(root, full=True))
    m2 = json.loads((root / ".myagent" / "manifest.json").read_text(encoding="utf-8"))
    assert m2["docs"]["API.md"]["doc_version"] == 2