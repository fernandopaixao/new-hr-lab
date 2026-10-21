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
    # Which LLM answers the agents: ollama, anthropic, openai or gemini (see llm.py).
    "llm_provider": os.getenv("LLM_PROVIDER", "ollama"),
    "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    "ollama_model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
    "ollama_timeout_s": int(os.getenv("OLLAMA_TIMEOUT_S", "180")),
    "ollama_num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "8192")),
    "ollama_num_predict": int(os.getenv("OLLAMA_NUM_PREDICT", "900")),
    "ollama_keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
    "ollama_max_concurrency": int(os.getenv("OLLAMA_MAX_CONCURRENCY", "1")),
    "ollama_temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0")),
    # Cloud providers. API keys are not settings: see apikeys.py.
    "anthropic_model": os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5"),
    "anthropic_effort": os.getenv("ANTHROPIC_EFFORT", "medium"),
    "openai_model": os.getenv("OPENAI_MODEL", "gpt-5-mini"),
    "openai_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    "cloud_timeout_s": int(os.getenv("CLOUD_TIMEOUT_S", "120")),
    "cloud_max_tokens": int(os.getenv("CLOUD_MAX_TOKENS", "16000")),
    "cloud_max_concurrency": int(os.getenv("CLOUD_MAX_CONCURRENCY", "4")),
    # Spending cap of the external providers in US$ (see budget.py). 0 blocks every external call.
    "spend_cap_usd": float(os.getenv("SPEND_CAP_USD", "10")),
    # MENSAL: the counter restarts each calendar month (UTC); TOTAL: never restarts.
    "spend_period": os.getenv("SPEND_PERIOD", "MENSAL"),
    # A log entry is written when the spend passes this share of the cap.
    "spend_alert_percent": float(os.getenv("SPEND_ALERT_PERCENT", "80")),
    "agent_cache_enabled": _bool("AGENT_CACHE_ENABLED", True),
    # Engine of the eligibility and audit agents (see engines.py): qwen (generative model of the
    # provider above, qwen2.5:7b by default) or jev (JEV-style decision model served by Ollama).
    "agent_engine": os.getenv("AGENT_ENGINE", "qwen"),
    "jev_model": os.getenv("JEV_MODEL", "tev1:0.8b"),
    "jev_base_url": os.getenv("JEV_BASE_URL", ""),  # empty: the same Ollama as ollama_base_url
    "jev_timeout_s": int(os.getenv("JEV_TIMEOUT_S", "30")),
    "jev_max_concurrency": int(os.getenv("JEV_MAX_CONCURRENCY", "2")),
    # The agent also classifies eligibility (advisory: the rules still decide).
    "agent_eligibility_enabled": _bool("AGENT_ELIGIBILITY_ENABLED", True),
    # The other engine answers the same task right after, for comparison only (never decides).
    "agent_compare_enabled": _bool("AGENT_COMPARE_ENABLED", False),
    # When Ollama is unreachable the flow parks and waits, unless this is enabled.
    "heuristic_fallback_enabled": _bool("HEURISTIC_FALLBACK_ENABLED", False),
    # SEMPRE: every plan and audit needs a human decision.
    # SE_REPROVADO: human decision only when the agent or the rules reprove.
    "human_review_mode": os.getenv("HUMAN_REVIEW_MODE", "SE_REPROVADO"),
    "stage_delay_ms": int(os.getenv("STAGE_DELAY_MS", "700")),
    "failure_rate_percent": float(os.getenv("FAILURE_RATE_PERCENT", "0")),
    # Phase 2: embeddings of every event and the natural language agent.
    # ollama, openai, gemini or simulado (hashing, no AI).
    "embedding_provider": os.getenv("EMBEDDING_PROVIDER", "ollama"),
    "embedding_model": os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
    "openai_embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
    "gemini_embedding_model": os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
    "indexing_enabled": _bool("INDEXING_ENABLED", True),
    "ask_model": os.getenv("ASK_MODEL", ""),  # empty: same model as the review agent
    "ask_top_k": int(os.getenv("ASK_TOP_K", "8")),
}

SETTING_TYPES = {k: type(v) for k, v in DEFAULT_SETTINGS.items()}
HUMAN_REVIEW_MODES = ("SEMPRE", "SE_REPROVADO")
CHOICES = {
    "llm_provider": ("ollama", "anthropic", "openai", "gemini"),
    "agent_engine": ("qwen", "jev"),
    "embedding_provider": ("ollama", "openai", "gemini", "simulado"),
    "anthropic_effort": ("", "low", "medium", "high", "xhigh", "max"),
    "spend_period": ("MENSAL", "TOTAL"),
}


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
    for key, allowed in CHOICES.items():
        if key in out and out[key] not in allowed:
            raise ValueError(f"{key} deve ser um de {allowed}")
    for key in ("spend_cap_usd", "spend_alert_percent"):
        if key in out and out[key] < 0:
            raise ValueError(f"{key} não pode ser negativo")
    if "human_review_mode" in out and out["human_review_mode"] not in HUMAN_REVIEW_MODES:
        raise ValueError(f"human_review_mode deve ser um de {HUMAN_REVIEW_MODES}")
    return out
