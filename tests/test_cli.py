import subprocess
import sys
from pathlib import Path

from myagent.cli import main
from myagent.report import compute_exit_code
from myagent.types import DocResult, RunReport, Verdict

ROOT = Path(__file__).resolve().parents[1]


def test_version_flag():
    r = subprocess.run(
        [sys.executable, str(ROOT / "myagent.py"), "--version"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "myagent" in r.stdout.lower()


def test_help_flag():
    r = subprocess.run(
        [sys.executable, str(ROOT / "myagent.py"), "--help"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "usage" in r.stdout.lower()


def test_run_offline_fixture(fixture_repo):
    root = fixture_repo("fastapi_app")
    code = main([str(root), "--offline", "-q"])
    assert code == 0
    assert (root / "docs" / "API.md").is_file()
    assert (root / "docs" / "BLUEPRINT.md").is_file()


def test_nonexistent_path_exit_2(tmp_path):
    assert main([str(tmp_path / "nope"), "--offline", "-q"]) == 2


def test_file_target_exit_3(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert main([str(f), "--offline", "-q"]) == 3


def test_unknown_role_exit_2(fixture_repo):
    root = fixture_repo("fastapi_app")
    assert main([str(root), "--offline", "--only", "NOPE", "-q"]) == 2


def test_dry_run_prints_plan(fixture_repo, capsys):
    root = fixture_repo("fastapi_app")
    code = main([str(root), "--offline", "--dry-run"])
    assert code == 0
    assert not (root / "docs").exists()
    out = capsys.readouterr().out
    assert "API" in out


def test_exit_code_4_on_flagged():
    rep = RunReport(docs=[
        DocResult(role_id="API", filename="API.md",
                  verdict=Verdict(approved=False)),
    ])
    assert compute_exit_code(rep) == 4


def test_exit_code_0_on_approved():
    rep = RunReport(docs=[
        DocResult(role_id="API", filename="API.md",
                  verdict=Verdict(approved=True)),
    ])
    assert compute_exit_code(rep) == 0