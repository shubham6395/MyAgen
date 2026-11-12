from __future__ import annotations

import json
import logging
import random
import re
import ssl
import time
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from myagent.types import Config

log = logging.getLogger("myagent.llm")

_OVERFLOW = re.compile(r"context|token.*limit|maximum.*length", re.I)
_RETRYABLE = {429, 500, 502, 503, 504}
_READ_CAP = 10_000_000


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


class ContextOverflowError(LLMError):
    pass


class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str, *, max_tokens: int | None = None,
                 json_mode: bool = False) -> str: ...


class NullLLM:
    name = "none"

    def complete(self, system: str, user: str, *, max_tokens: int | None = None,
                 json_mode: bool = False) -> str:
        raise LLMUnavailable("offline mode: no LLM configured")


def _http_post_json(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        raw = resp.read(_READ_CAP)
    return json.loads(raw)


class _BaseLLM:
    name = "base"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _endpoint(self) -> tuple[str, dict]:
        raise NotImplementedError

    def _payload(self, system: str, user: str, max_tokens: int | None, json_mode: bool) -> dict:
        raise NotImplementedError

    def _parse(self, data: dict) -> str:
        raise NotImplementedError

    def complete(self, system: str, user: str, *, max_tokens: int | None = None,
                 json_mode: bool = False) -> str:
        url, headers = self._endpoint()
        payload = self._payload(system, user, max_tokens, json_mode)
        attempts = self.cfg.max_retries + 1
        for attempt in range(attempts):
            try:
                data = _http_post_json(url, headers, payload, self.cfg.timeout)
                return self._parse(data)
            except HTTPError as e:
                try:
                    body = e.read(_READ_CAP).decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                if e.code == 400 and _OVERFLOW.search(body):
                    raise ContextOverflowError(body[:300]) from e
                if e.code in _RETRYABLE and attempt < attempts - 1:
                    delay = min(30.0, 2.0 ** attempt) + random.uniform(0, 1)
                    retry_after = e.headers.get("Retry-After") if e.headers else None
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                    log.warning("HTTP %s, retry %d/%d in %.1fs", e.code, attempt + 1,
                                self.cfg.max_retries, delay)
                    time.sleep(delay)
                    continue
                raise LLMError(f"HTTP {e.code}: {body[:300]}") from e
            except (URLError, TimeoutError, OSError) as e:
                if attempt < attempts - 1:
                    delay = min(30.0, 2.0 ** attempt) + random.uniform(0, 1)
                    log.warning("network error (%s), retry %d/%d", e, attempt + 1,
                                self.cfg.max_retries)
                    time.sleep(delay)
                    continue
                raise LLMError(f"network error: {e}") from e
        raise LLMError("unreachable")


class OpenAICompatLLM(_BaseLLM):
    name = "openai-compatible"

    def _endpoint(self) -> tuple[str, dict]:
        base = (self.cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        return base + "/chat/completions", headers

    def _payload(self, system, user, max_tokens, json_mode) -> dict:
        payload = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.cfg.temperature,
            "max_tokens": max_tokens or self.cfg.max_output_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _parse(self, data: dict) -> str:
        if "error" in data:
            raise LLMError(f"API error: {data['error']}")
        return data["choices"][0]["message"]["content"]


class AnthropicLLM(_BaseLLM):
    name = "anthropic"

    def _endpoint(self) -> tuple[str, dict]:
        base = (self.cfg.base_url or "https://api.anthropic.com").rstrip("/")
        headers = {
            "x-api-key": self.cfg.api_key or "",
            "anthropic-version": "2023-06-01",
        }
        return base + "/v1/messages", headers

    def _payload(self, system, user, max_tokens, json_mode) -> dict:
        return {
            "model": self.cfg.model,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "max_tokens": max_tokens or self.cfg.max_output_tokens,
            "temperature": self.cfg.temperature,
        }

    def _parse(self, data: dict) -> str:
        if data.get("stop_reason") == "max_tokens":
            log.warning("Anthropic response truncated at max_tokens")
        return "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")


def make_client(cfg: Config) -> LLMClient:
    if cfg.offline or cfg.provider == "none":
        return NullLLM()
    if cfg.provider == "anthropic":
        return AnthropicLLM(cfg)
    return OpenAICompatLLM(cfg)