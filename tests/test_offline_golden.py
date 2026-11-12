from pathlib import Path

from myagent import roles
from myagent.analyzer import analyze_repo
from myagent.render import RENDERERS
from myagent.render.assemble import assemble_doc

GOLDEN = Path(__file__).parent / "golden"


def _offline_doc(fixture_repo, repo_name, role_id):
    f = analyze_repo(fixture_repo(repo_name))
    role = roles.get_role(role_id)
    _, sources = roles.build_context(role, f)
    return assemble_doc(role, f, {}, "offline", "0" * 64, sources)


def test_express_readme_golden(fixture_repo):
    md = _offline_doc(fixture_repo, "express_app", "README")
    expected = (GOLDEN / "express_README.md").read_text(encoding="utf-8")
    assert md == expected


def test_express_api_golden(fixture_repo):
    md = _offline_doc(fixture_repo, "express_app", "API")
    expected = (GOLDEN / "express_API.md").read_text(encoding="utf-8")
    assert md == expected


def test_fastapi_database_fragment(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    frag = RENDERERS["model_tables"](f, roles.get_role("DATABASE"))
    expected = (GOLDEN / "fastapi_DATABASE_fragment.md").read_text(encoding="utf-8")
    assert frag == expected


def test_fastapi_setup_fragment(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    frag = RENDERERS["env_table"](f, roles.get_role("SETUP"))
    expected = (GOLDEN / "fastapi_SETUP_fragment.md").read_text(encoding="utf-8")
    assert frag == expected


def test_offline_determinism(fixture_repo):
    root = fixture_repo("express_app")
    role = roles.get_role("API")
    docs = []
    for _ in range(2):
        f = analyze_repo(root)
        _, sources = roles.build_context(role, f)
        docs.append(assemble_doc(role, f, {}, "offline", "0" * 64, sources))
    assert docs[0] == docs[1]