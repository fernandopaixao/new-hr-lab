"""API keys of the cloud LLM providers.

Order of precedence: the environment (.env, read by docker compose) and then
the file `secrets.json` in DATA_DIR, written by the setup wizard. DATA_DIR is the
volume shared by the API, the workers and the indexer, so a key saved in the
interface reaches all of them. Keys are never returned by the API, never logged
and never stored in Redis; only the last four characters are shown.
"""
from __future__ import annotations

import json
import os
import tempfile

from . import config

ENV_KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def _path() -> str:
    return os.path.join(config.DATA_DIR, "secrets.json")


def _read() -> dict[str, str]:
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _from_env(provider: str) -> str:
    for name in ENV_KEYS.get(provider, ()):
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def get_key(provider: str) -> str:
    return _from_env(provider) or str(_read().get(provider) or "").strip()


def set_key(provider: str, key: str | None) -> None:
    """Saves (or, with an empty key, removes) the key of one provider."""
    if provider not in ENV_KEYS:
        raise ValueError(f"provedor sem chave de API: {provider}")
    data = _read()
    key = (key or "").strip()
    if key:
        data[provider] = key
    else:
        data.pop(provider, None)
    os.makedirs(config.DATA_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=config.DATA_DIR, prefix=".secrets-")
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, _path())
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def status() -> dict[str, dict]:
    """What the interface may know about each key: whether it exists, where it comes from, its last four characters."""
    stored = _read()
    out = {}
    for provider in ENV_KEYS:
        env = _from_env(provider)
        key = env or str(stored.get(provider) or "")
        out[provider] = {"configurada": bool(key), "origem": "ambiente (.env)" if env else ("assistente" if key else None),
                         "final": key[-4:] if len(key) >= 12 else None}
    return out
