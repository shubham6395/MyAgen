from pathlib import Path

from myagent import util


def test_sha256_file_known_vector(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"hello")
    assert util.sha256_file(p) == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_read_text_safe_strips_bom(tmp_path):
    p = tmp_path / "b.txt"
    p.write_bytes(b"\xef\xbb\xbfhi")
    assert util.read_text_safe(p) == "hi"


def test_read_text_safe_binary_returns_none(tmp_path):
    p = tmp_path / "c.bin"
    p.write_bytes(b"\x00\x01\x02")
    assert util.read_text_safe(p) is None


def test_read_text_safe_replaces_invalid_utf8(tmp_path):
    p = tmp_path / "d.txt"
    p.write_bytes(b"caf\xe9")
    assert util.read_text_safe(p) == "caf\ufffd"


def test_glob_match_doublestar_dirs():
    assert util.glob_match("**/routes/**", "src/routes/users.js")
    assert util.glob_match("**/routes/**", "routes/users.js")
    assert not util.glob_match("**/routes/**", "src/routers/users.js")


def test_glob_match_basename_when_no_slash():
    assert util.glob_match("*.sql", "db/schema.sql")
    assert util.glob_match("README*", "README.md")
    assert util.glob_match("Dockerfile*", "docker/Dockerfile.prod")
    assert not util.glob_match("*.sql", "db/schema.sql.bak")


def test_glob_match_single_star_does_not_cross_dirs():
    assert util.glob_match("src/*.js", "src/a.js")
    assert not util.glob_match("src/*.js", "src/sub/a.js")


def test_glob_match_test_patterns():
    assert util.glob_match("**/test_*.py", "tests/test_main.py")
    assert util.glob_match("**/*.test.*", "src/users.test.js")
    assert util.glob_match("**/*.spec.*", "a/b/c.spec.ts")
    assert not util.glob_match("**/migrations/**", "alembic/versions/0001.py")


def test_glob_match_bare_doublestar_matches_all():
    assert util.glob_match("**", "a/b/c.txt")


def test_redact_secrets_masks_api_keys():
    text = (
        "key=sk-abcdefghijklmnopqrstuvwx and AKIAIOSFODNN7EXAMPLE "
        "and ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    )
    out = util.redact_secrets(text)
    assert "sk-abcdefghijklmnopqrstuvwx" not in out
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "ghp_abcdefghijklmnopqrstuvwxyz" not in out
    assert "[REDACTED]" in out


def test_redact_secrets_masks_private_key_block():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEabc\n-----END RSA PRIVATE KEY-----"
    out = util.redact_secrets(text)
    assert "MIIEabc" not in out
    assert "[REDACTED]" in out


def test_redact_secrets_leaves_normal_text():
    text = "DATABASE_URL=postgres://localhost/db\nDEBUG=true"
    assert util.redact_secrets(text) == text


def test_estimate_tokens():
    assert util.estimate_tokens("abcd" * 4) == 4
    assert util.estimate_tokens("") == 0


def test_truncate():
    assert util.truncate("abcdef", 10) == "abcdef"
    assert util.truncate("abcdef", 3) == "abc..."


def test_posix_rel():
    root = Path("C:/repo")
    assert util.posix_rel(root / "src" / "a.py", root) == "src/a.py"