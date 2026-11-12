from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from myagent.types import Config

log = logging.getLogger("myagent.config")

PROVIDER_DEFAULTS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
    "ollama": ("http://localhost:11434/v1", "llama3.1"),
    "lmstudio": ("http://localhost:1234/v1", None),
    "anthropic": ("https://api.anthropic.com", "claude-sonnet-4-5"),
}
REMOTE = {"openai", "openrouter", "anthropic"}
LOCAL = {"ollama", "lmstudio"}
VALID_PROVIDERS = set(PROVIDER_DEFAULTS) | {"none", "auto"}


def probe(base_url: str, timeout: float = 3.0) -> bool:
    from urllib.request import urlopen
    try:
        with urlopen(base_url.rstrip("/") + "/models", timeout=timeout) as resp:
            resp.read(1024)
        return True
    except Exception:
        return False


def _load_config_file(target: Path, explicit: Path | None) -> dict:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path(target) / "myagent.config.json")
    candidates.append(Path(__file__).resolve().parent.parent / "myagent.config.json")
    for path in candidates:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                log.warning("ignoring config file %s: %s", path, e)
                return {}
    return {}


def resolve_config(target: Path, overrides: dict | None = None) -> Config:
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    file_cfg = _load_config_file(Path(target), overrides.get("config_file"))

    def pick(key: str, env: str | None = None, default=None):
        if key in overrides:
            return overrides[key]
        if env and os.environ.get(env):
            return os.environ[env]
        if key in file_cfg:
            return file_cfg[key]
        return default

    provider = str(pick("provider", "MYAGENT_PROVIDER", "auto"))
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"unknown provider: {provider!r} (valid: {', '.join(sorted(VALID_PROVIDERS))})")

    api_key = pick("api_key", "MYAGENT_API_KEY")
    if provider == "auto":
        if api_key or os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        else:
            provider = "none"
    if not api_key:
        if provider in ("openai", "openrouter"):
            api_key = os.environ.get("OPENAI_API_KEY")
        elif provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY")

    default_base, default_model = PROVIDER_DEFAULTS.get(provider, (None, None))
    base_url = pick("base_url", "MYAGENT_BASE_URL", default_base)
    model = pick("model", "MYAGENT_MODEL", default_model)

    return Config(
        target=Path(target),
        out=Path(overrides["out"]) if overrides.get("out") else None,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        offline=bool(pick("offline", None, False)),
        only=overrides.get("only"),
        full=bool(overrides.get("full", False)),
        max_rounds=int(pick("max_rounds", None, 2)),
        concurrency=int(pick("concurrency", None, 4)),
        dry_run=bool(overrides.get("dry_run", False)),
        timeout=float(pick("timeout", "MYAGENT_TIMEOUT", 120.0)),
        max_retries=int(pick("max_retries", None, 3)),
        context_tokens=int(pick("context_tokens", "MYAGENT_CONTEXT_TOKENS", 16000)),
        max_output_tokens=int(pick("max_output_tokens", "MYAGENT_MAX_OUTPUT_TOKENS", 8000)),
        temperature=float(pick("temperature", None, 0.2)),
        verbose=bool(overrides.get("verbose", False)),
        quiet=bool(overrides.get("quiet", False)),
        config_file=Path(overrides["config_file"]) if overrides.get("config_file") else None,
    )


def detect_offline(cfg: Config) -> tuple[bool, str]:
    if cfg.offline or cfg.provider == "none":
        return True, "offline mode requested"
    if cfg.provider in REMOTE and not cfg.api_key:
        return True, f"no API key for provider {cfg.provider!r} (set MYAGENT_API_KEY)"
    if cfg.provider in LOCAL:
        if not probe(cfg.base_url or "", 3.0):
            return True, f"local server unreachable at {cfg.base_url}"
    return False, ""