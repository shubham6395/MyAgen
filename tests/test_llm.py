import io
import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from myagent import config, llm
from myagent.types import Config


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self, n=-1):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(responses):
    calls = []

    def _fake(req, timeout=None, context=None):
        calls.append(req)
        r = responses[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return FakeResponse(r)

    return _fake, calls


def http_error(code, body="err", headers=None):
    msg = Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return HTTPError("http://x", code, "err", msg, io.BytesIO(body.encode()))


def cfg(**kw):
    base = dict(target=Path("."), provider="openai", model="gpt-4o-mini",
                api_key="k", base_url="https://api.openai.com/v1",
                max_retries=3, timeout=5, max_output_tokens=1000, temperature=0.2)
    base.update(kw)
    return Config(**base)


def test_openai_request_and_parse(monkeypatch):
    payload = {"choices": [{"message": {"content": "hello"}}]}
    fake, calls = fake_urlopen([payload])
    monkeypatch.setattr(llm, "urlopen", fake)
    client = llm.OpenAICompatLLM(cfg())
    out = client.complete("sys", "user")
    assert out == "hello"
    req = calls[0]
    assert req.full_url == "https://api.openai.com/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer k"
    body = json.loads(req.data)
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1] == {"role": "user", "content": "user"}
    assert body["max_tokens"] == 1000


def test_anthropic_request_and_parse(monkeypatch):
    payload = {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
               "stop_reason": "end_turn"}
    fake, calls = fake_urlopen([payload])
    monkeypatch.setattr(llm, "urlopen", fake)
    client = llm.AnthropicLLM(cfg(provider="anthropic", model="claude-sonnet-4-5",
                                  base_url="https://api.anthropic.com"))
    out = client.complete("sys", "user")
    assert out == "ab"
    req = calls[0]
    assert req.full_url == "https://api.anthropic.com/v1/messages"
    assert req.headers["X-api-key"] == "k"
    assert req.headers["Anthropic-version"] == "2023-06-01"
    body = json.loads(req.data)
    assert body["system"] == "sys"
    assert body["messages"] == [{"role": "user", "content": "user"}]
    assert body["max_tokens"] == 1000


def test_retry_on_429_then_success(monkeypatch):
    slept = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    fake, calls = fake_urlopen([
        http_error(429, "rate limited", {"Retry-After": "0"}),
        {"choices": [{"message": {"content": "ok"}}]},
    ])
    monkeypatch.setattr(llm, "urlopen", fake)
    assert llm.OpenAICompatLLM(cfg()).complete("s", "u") == "ok"
    assert len(calls) == 2
    assert slept


def test_no_retry_on_401(monkeypatch):
    fake, calls = fake_urlopen([http_error(401, "bad key")])
    monkeypatch.setattr(llm, "urlopen", fake)
    with pytest.raises(llm.LLMError):
        llm.OpenAICompatLLM(cfg()).complete("s", "u")
    assert len(calls) == 1


def test_context_overflow_raises_special_error(monkeypatch):
    fake, _ = fake_urlopen([http_error(400, "maximum context length exceeded")])
    monkeypatch.setattr(llm, "urlopen", fake)
    with pytest.raises(llm.ContextOverflowError):
        llm.OpenAICompatLLM(cfg()).complete("s", "u")


def test_network_error_retries_then_fails(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    fake, calls = fake_urlopen([URLError("down"), URLError("down"),
                                URLError("down"), URLError("down")])
    monkeypatch.setattr(llm, "urlopen", fake)
    with pytest.raises(llm.LLMError):
        llm.OpenAICompatLLM(cfg(max_retries=3)).complete("s", "u")
    assert len(calls) == 4


def test_200_with_error_body_raises(monkeypatch):
    fake, _ = fake_urlopen([{"error": {"message": "proxy failure"}}])
    monkeypatch.setattr(llm, "urlopen", fake)
    with pytest.raises(llm.LLMError):
        llm.OpenAICompatLLM(cfg()).complete("s", "u")


def test_null_llm_raises_unavailable():
    with pytest.raises(llm.LLMUnavailable):
        llm.NullLLM().complete("s", "u")


def test_config_precedence(tmp_path, monkeypatch):
    (tmp_path / "myagent.config.json").write_text(
        json.dumps({"provider": "ollama", "model": "file-model", "timeout": 9}),
        encoding="utf-8")
    monkeypatch.setenv("MYAGENT_PROVIDER", "openrouter")
    monkeypatch.setenv("MYAGENT_MODEL", "env-model")
    monkeypatch.delenv("MYAGENT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = config.resolve_config(tmp_path, {"model": "cli-model"})
    assert c.provider == "openrouter"
    assert c.model == "cli-model"
    assert c.timeout == 9.0
    assert c.base_url == "https://openrouter.ai/api/v1"


def test_config_auto_provider_openai_key(tmp_path, monkeypatch):
    for var in ("MYAGENT_PROVIDER", "MYAGENT_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    c = config.resolve_config(tmp_path, {})
    assert c.provider == "openai"
    assert c.api_key == "sk-test"


def test_offline_detection_no_key(tmp_path, monkeypatch):
    for var in ("MYAGENT_PROVIDER", "MYAGENT_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    c = config.resolve_config(tmp_path, {"provider": "openai"})
    offline, reason = config.detect_offline(c)
    assert offline and "key" in reason.lower()


def test_offline_flag_wins(tmp_path):
    c = config.resolve_config(tmp_path, {"provider": "openai", "api_key": "k", "offline": True})
    offline, _ = config.detect_offline(c)
    assert offline


def test_local_probe_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "probe", lambda base, timeout=3: False)
    c = config.resolve_config(tmp_path, {"provider": "ollama"})
    offline, reason = config.detect_offline(c)
    assert offline and "unreachable" in reason.lower()


def test_local_probe_reachable(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "probe", lambda base, timeout=3: True)
    c = config.resolve_config(tmp_path, {"provider": "ollama"})
    offline, _ = config.detect_offline(c)
    assert not offline