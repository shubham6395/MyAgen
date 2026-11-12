import pytest

from myagent.analyzer import python as pyx


def test_symbols(fixture_repo):
    root = fixture_repo("fastapi_app")
    out = pyx.extract("main.py", (root / "main.py").read_text(encoding="utf-8"))
    names = {s["name"] for s in out["symbols"]}
    assert {"get_current_user", "list_items", "create_item", "read_me"} <= names
    li = next(s for s in out["symbols"] if s["name"] == "list_items")
    assert li["kind"] == "function"
    assert li["file"] == "main.py"
    assert "db" in li["signature"]


def test_routes(fixture_repo):
    root = fixture_repo("fastapi_app")
    out = pyx.extract("main.py", (root / "main.py").read_text(encoding="utf-8"))
    routes = {(r["method"], r["path"]) for r in out["routes"]}
    assert routes == {
        ("GET", "/items"), ("POST", "/items"),
        ("GET", "/items/{item_id}"), ("PUT", "/items/{item_id}"),
        ("DELETE", "/items/{item_id}"), ("GET", "/users/me"),
    }
    assert all(r["framework"] == "fastapi" for r in out["routes"])
    me = next(r for r in out["routes"] if r["path"] == "/users/me")
    assert me["auth_hints"]
    li = next(r for r in out["routes"] if r["path"] == "/items" and r["method"] == "GET")
    assert not li["auth_hints"]


def test_models(fixture_repo):
    root = fixture_repo("fastapi_app")
    out = pyx.extract("models.py", (root / "models.py").read_text(encoding="utf-8"))
    models = {m["name"]: m for m in out["models"]}
    assert set(models) == {"User", "Item"}
    assert models["User"]["table"] == "users"
    assert models["User"]["orm"] == "sqlalchemy"
    email = next(f for f in models["User"]["fields"] if f["name"] == "email")
    assert email["nullable"] is False
    uid = next(f for f in models["User"]["fields"] if f["name"] == "id")
    assert uid["primary_key"] is True
    assert {r["target"] for r in models["User"]["relationships"]} == {"Item"}
    owner = next(f for f in models["Item"]["fields"] if f["name"] == "owner_id")
    assert "users.id" in " ".join(owner["constraints"])


def test_imports_internal_external(fixture_repo):
    root = fixture_repo("fastapi_app")
    module_map = {"database": "database.py", "models": "models.py", "main": "main.py"}
    out = pyx.extract("main.py", (root / "main.py").read_text(encoding="utf-8"), module_map)
    internal = {i["target"] for i in out["imports"] if i["kind"] == "internal"}
    external = {i["target"] for i in out["imports"] if i["kind"] == "external"}
    assert {"database.py", "models.py"} <= internal
    assert "fastapi" in external


def test_syntax_error_raises():
    with pytest.raises(SyntaxError):
        pyx.extract("bad.py", "def broken(:\n")