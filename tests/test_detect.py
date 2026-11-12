from myagent import facts
from myagent.analyzer import analyze_repo


def test_fastapi_facts(fixture_repo):
    f = analyze_repo(fixture_repo("fastapi_app"))
    facts.validate_facts(f)
    assert len(f["routes"]) == 6
    assert {m["name"] for m in f["models"]} == {"User", "Item"}
    deps = {d["name"] for d in f["dependencies"]["runtime"]}
    assert {"fastapi", "sqlalchemy"} <= deps
    assert "fastapi" in {x["name"] for x in f["frameworks"]}
    env = {e["name"]: e for e in f["env_vars"]}
    assert env["SECRET_KEY"]["secret_like"] is True
    assert env["DATABASE_URL"]["default"] == "sqlite:///./app.db"
    assert "pytest" in f["tests"]["frameworks"]
    assert f["migrations"] and f["migrations"][0]["tool"] == "alembic"
    assert any(e["file"] == "main.py" for e in f["entrypoints"])
    assert f["repo"]["primary_language"] == "Python"


def test_express_facts(fixture_repo):
    f = analyze_repo(fixture_repo("express_app"))
    routes = {(r["method"], r["path"]) for r in f["routes"]}
    assert routes == {
        ("GET", "/health"), ("GET", "/users"),
        ("POST", "/users"), ("GET", "/users/:id"),
    }
    assert any(i["service"] == "stripe" for i in f["integrations"])
    assert any(p["kind"] == "jwt" for p in f["auth"]["patterns"])
    scripts = {
        c["name"]
        for s in f["scripts"] if s["kind"] == "package-json"
        for c in s["commands"]
    }
    assert {"start", "dev", "test"} <= scripts
    assert "jest" in f["tests"]["frameworks"]
    env = {e["name"] for e in f["env_vars"]}
    assert {"PORT", "JWT_SECRET", "MONGODB_URI", "STRIPE_KEY"} <= env


def test_polyglot_facts(fixture_repo):
    f = analyze_repo(fixture_repo("polyglot_repo"))
    servers = f["mcp"]["configs"][0]["servers"]
    assert servers[0]["name"] == "filesystem"
    assert servers[0]["env_keys"] == ["API_KEY"]
    assert "super-secret-value" not in facts.canonical_json(f)
    models = {m["name"]: m for m in f["models"]}
    assert {"customers", "orders"} <= set(models)
    assert models["customers"]["orm"] == "raw_sql"
    names = {s["name"] for s in f["symbols"]}
    assert "Add" in names and "greet" in names
    mk = [s for s in f["scripts"] if s["kind"] == "makefile"]
    assert mk and {"build", "test"} <= {c["name"] for c in mk[0]["commands"]}


def test_excerpts_and_evidence_redacted(tmp_path):
    (tmp_path / "main.py").write_text(
        'API_KEY = "sk-abcdefghijklmnopqrstuvwx"\n', encoding="utf-8"
    )
    f = analyze_repo(tmp_path)
    assert "sk-abcdefghijklmnopqrstuvwx" not in facts.canonical_json(f)


def test_ci_detection(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(
        "name: CI\njobs:\n  test:\n    steps:\n      - run: pytest\n",
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    f = analyze_repo(tmp_path)
    assert f["ci"] and f["ci"][0]["kind"] == "github-actions"
    assert f["ci"][0]["jobs"][0]["name"] == "test"