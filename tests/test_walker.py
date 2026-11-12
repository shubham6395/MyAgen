from myagent import util
from myagent.analyzer import walker


def _write(root, rel, content="x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_default_ignores(tmp_path):
    _write(tmp_path, "node_modules/lib/a.js")
    _write(tmp_path, ".git/config")
    _write(tmp_path, "__pycache__/a.pyc")
    _write(tmp_path, "src/a.py", "print(1)")
    res = walker.walk_repo(tmp_path)
    assert {f["path"] for f in res["files"]} == {"src/a.py"}


def test_gitignore_semantics(fixture_repo):
    root = fixture_repo("polyglot_repo")
    paths = {f["path"] for f in walker.walk_repo(root)["files"]}
    assert "build/out.o" not in paths
    assert "rootonly.txt" not in paths
    assert "sub/rootonly.txt" in paths
    assert "a.tmp" not in paths
    assert "important.tmp" in paths
    assert "nested/ignore.txt" not in paths
    assert "nested/other.txt" in paths
    assert ".gitignore" in paths


def test_hashing_and_determinism(tmp_path):
    _write(tmp_path, "a.py", "print(1)\n")
    r1 = walker.walk_repo(tmp_path)
    r2 = walker.walk_repo(tmp_path)
    assert r1["files"] == r2["files"]
    rec = r1["files"][0]
    assert rec["sha256"] == util.sha256_file(tmp_path / "a.py")
    assert rec["language"] == "Python"
    assert rec["loc"] == 1


def test_binary_hashed_but_not_text(tmp_path):
    (tmp_path / "img.png").write_bytes(b"\x89PNG\x00\x01")
    _write(tmp_path, "a.py", "x = 1")
    res = walker.walk_repo(tmp_path)
    assert "img.png" in {f["path"] for f in res["files"]}
    assert "img.png" not in res["texts"]
    assert res["texts"]["a.py"] == "x = 1"


def test_role_hints(tmp_path):
    _write(tmp_path, "tests/test_a.py", "def test_a(): pass")
    _write(tmp_path, "package.json", "{}")
    _write(tmp_path, "README.md", "# hi")
    _write(tmp_path, "scripts/setup.sh", "echo hi")
    _write(tmp_path, "src/a.py", "x = 1")
    hints = {f["path"]: f["role_hint"] for f in walker.walk_repo(tmp_path)["files"]}
    assert hints["tests/test_a.py"] == "test"
    assert hints["package.json"] == "config"
    assert hints["README.md"] == "docs"
    assert hints["scripts/setup.sh"] == "script"
    assert hints["src/a.py"] == "source"


def test_extra_skip_out_dir(tmp_path):
    _write(tmp_path, "docs/API.md", "# api")
    _write(tmp_path, "a.py", "x = 1")
    res = walker.walk_repo(tmp_path, extra_skip={"docs"})
    assert "docs/API.md" not in {f["path"] for f in res["files"]}


def test_file_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(walker, "MAX_FILES", 2)
    for i in range(5):
        _write(tmp_path, f"f{i}.py", "x = 1")
    res = walker.walk_repo(tmp_path)
    assert len(res["files"]) == 2
    assert res["truncation"]["cap_hit"] is True