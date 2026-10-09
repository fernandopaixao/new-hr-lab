"""Static configuration (environment) and runtime-editable settings."""
from __future__ import annotations

import os
from typing import Any

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit-log.jsonl")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "sim", "on")


# Defaults for settings that can be changed at runtime from the interface.
DEFAULT_SETTINGS: dict[str, Any] = {
    "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    "ollama_model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
    "ollama_timeout_s": int(os.getenv("OLLAMA_TIMEOUT_S", "180")),
    "ollama_num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "8192")),
    "ollama_num_predict": int(os.getenv("OLLAMA_NUM_PREDICT", "900")),
    "ollama_keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
    "ollama_max_concurrency": int(os.getenv("OLLAMA_MAX_CONCURRENCY", "1")),
    "ollama_temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0")),
    "agent_cache_enabled": _bool("AGENT_CACHE_ENABLED", True),
    # When Ollama is unreachable the flow parks and waits, unless this is enabled.
    "heuristic_fallback_enabled": _bool("HEURISTIC_FALLBACK_ENABLED", False),
    # SEMPRE: every plan and audit needs a human decision.
    # SE_REPROVADO: human decision only when the agent or the rules reprove.
    "human_review_mode": os.getenv("HUMAN_REVIEW_MODE", "SE_REPROVADO"),
    "stage_delay_ms": int(os.getenv("STAGE_DELAY_MS", "700")),
    "failure_rate_percent": float(os.getenv("FAILURE_RATE_PERCENT", "0")),
}

SETTING_TYPES = {k: type(v) for k, v in DEFAULT_SETTINGS.items()}
HUMAN_REVIEW_MODES = ("SEMPRE", "SE_REPROVADO")


def coerce_settings(patch: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in patch.items():
        if key not in SETTING_TYPES:
            raise ValueError(f"configuração desconhecida: {key}")
        typ = SETTING_TYPES[key]
        if typ is bool:
            out[key] = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "sim", "on")
        else:
            out[key] = typ(value)
    if "human_review_mode" in out and out["human_review_mode"] not in HUMAN_REVIEW_MODES:
        raise ValueError(f"human_review_mode deve ser um de {HUMAN_REVIEW_MODES}")
    return out
