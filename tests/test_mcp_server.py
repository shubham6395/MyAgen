import io
import json
import sys

from myagent import mcp_server


def _req(mid, method, params=None):
    return {"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}


def test_initialize_handshake():
    resp = mcp_server.handle_message(_req(1, "initialize"))
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert resp["result"]["serverInfo"]["name"] == "myagent"
    assert "tools" in resp["result"]["capabilities"]


def test_initialized_notification_no_response():
    assert mcp_server.handle_message({"method": "notifications/initialized"}) is None


def test_ping():
    resp = mcp_server.handle_message(_req(2, "ping"))
    assert resp["result"] == {}


def test_tools_list():
    resp = mcp_server.handle_message(_req(3, "tools/list"))
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"document_codebase", "analyze_codebase", "get_docs_status"}
    for t in resp["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object"
        assert "target" in t["inputSchema"]["properties"]


def test_unknown_method():
    resp = mcp_server.handle_message(_req(4, "bogus/method"))
    assert resp["error"]["code"] == -32601


def test_tools_call_document_offline(fixture_repo):
    root = fixture_repo("express_app")
    resp = mcp_server.handle_message(_req(5, "tools/call", {
        "name": "document_codebase",
        "arguments": {"target": str(root), "offline": True},
    }))
    assert resp["result"]["isError"] is False
    assert len(list((root / "docs").glob("*.md"))) == 16
    assert "APPROVED" in resp["result"]["content"][0]["text"]


def test_tools_call_analyze(fixture_repo):
    root = fixture_repo("fastapi_app")
    resp = mcp_server.handle_message(_req(6, "tools/call", {
        "name": "analyze_codebase", "arguments": {"target": str(root)},
    }))
    text = resp["result"]["content"][0]["text"]
    assert "6" in text and "routes" in text


def test_tools_call_bad_target():
    resp = mcp_server.handle_message(_req(7, "tools/call", {
        "name": "analyze_codebase", "arguments": {"target": "Z:/does/not/exist"},
    }))
    assert resp["result"]["isError"] is True


def test_get_docs_status_empty(fixture_repo):
    root = fixture_repo("express_app")
    resp = mcp_server.handle_message(_req(8, "tools/call", {
        "name": "get_docs_status", "arguments": {"target": str(root)},
    }))
    assert "no docs" in resp["result"]["content"][0]["text"].lower()


def test_main_stdio_purity(fixture_repo, monkeypatch, capsys):
    root = fixture_repo("express_app")
    lines = [
        json.dumps(_req(1, "initialize")),
        json.dumps({"method": "notifications/initialized"}),
        json.dumps(_req(2, "tools/list")),
        json.dumps(_req(3, "tools/call", {
            "name": "analyze_codebase", "arguments": {"target": str(root)}})),
        "not json at all",
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(lines) + "\n"))
    code = mcp_server.main()
    assert code == 0
    out = capsys.readouterr().out
    parsed = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert len(parsed) == 4
    assert any(p.get("error", {}).get("code") == -32700 for p in parsed)