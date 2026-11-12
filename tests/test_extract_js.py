from myagent.analyzer import javascript as jsx


def test_routes_and_mounts(fixture_repo):
    root = fixture_repo("express_app")
    idx = jsx.extract("src/index.js", (root / "src/index.js").read_text(encoding="utf-8"))
    assert ("GET", "/health") in {(r["method"], r["path"]) for r in idx["routes"]}
    assert idx["mounts"] and idx["mounts"][0]["prefix"] == "/users"
    assert idx["mounts"][0]["source"] == "./routes/users"
    users = jsx.extract("src/routes/users.js", (root / "src/routes/users.js").read_text(encoding="utf-8"))
    routes = {(r["method"], r["path"]) for r in users["routes"]}
    assert routes == {("GET", "/"), ("POST", "/"), ("GET", "/:id")}
    by_id = next(r for r in users["routes"] if r["path"] == "/:id")
    assert by_id["auth_hints"]
    assert all(r["framework"] == "express" for r in users["routes"])


def test_mongoose_model(fixture_repo):
    root = fixture_repo("express_app")
    out = jsx.extract("src/models/user.js", (root / "src/models/user.js").read_text(encoding="utf-8"))
    assert len(out["models"]) == 1
    m = out["models"][0]
    assert m["name"] == "User"
    assert m["orm"] == "mongoose"
    fields = {f["name"]: f for f in m["fields"]}
    assert set(fields) == {"email", "name", "active"}
    assert fields["email"]["type"] == "String"


def test_components():
    out = jsx.extract(
        "src/Button.jsx",
        "export default function Button() { return <button>ok</button>; }",
    )
    comps = [s for s in out["symbols"] if s["kind"] == "component"]
    assert comps and comps[0]["name"] == "Button"


def test_imports(fixture_repo):
    root = fixture_repo("express_app")
    out = jsx.extract("src/index.js", (root / "src/index.js").read_text(encoding="utf-8"))
    internal = [i for i in out["imports"] if i["kind"] == "internal"]
    external = {i["target"] for i in out["imports"] if i["kind"] == "external"}
    assert internal and internal[0]["target"] == "./routes/users"
    assert "express" in external