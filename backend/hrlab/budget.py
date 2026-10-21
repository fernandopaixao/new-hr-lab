"""Spending cap of the external LLM providers (Anthropic, OpenAI, Google Gemini).

Every external call is priced from the token usage the provider returns times a
price table per model (US$ per million tokens). The cost is added to counters in
Redis, which survive restarts (AOF) and the lab reset:

- `hr:gastos:acum`   hash with the spend per period (`total`, `mes:2026-10`) and per
                     provider and model inside each period;
- `hr:gastos:log`    stream with one record per priced call (last 5000);
- `hr:gastos:precos` price overrides typed in the interface;
- `hr:gastos:bloqueio` set while the cap is reached, with when and why.

The cap and the prices are optional. Without a cap (0) the spend is only counted
and shown; nothing is blocked. With a cap, before each external call `check`
compares the spend of the current period plus the estimated cost of the prompt
with the cap. Once the cap is reached every new
external call is refused before it is sent: llm.py raises BudgetExceeded, which is
an AgentUnavailable, so cases wait as they do when the provider is down (or the
simulated agent answers, if enabled). Calls already in flight finish and are
charged, so the spend may pass the cap by at most those calls.

Ollama and the JEV decision model run locally and are never priced or blocked.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from . import logbook as log
from .store import P, Store, dumps, now_ms

ACC_KEY = f"{P}:gastos:acum"
LOG_KEY = f"{P}:gastos:log"
PRICES_KEY = f"{P}:gastos:precos"
BLOCK_KEY = f"{P}:gastos:bloqueio"
LOG_MAX = 5000
EXTERNAL = ("anthropic", "openai", "gemini")
NAMES = {"anthropic": "Anthropic", "openai": "OpenAI", "gemini": "Google Gemini"}
PERIODS = ("MENSAL", "TOTAL")
# Rough size of a token, used only to estimate a prompt before it is sent.
CHARS_PER_TOKEN = 4

logger = logging.getLogger("hrlab.gastos")

# US$ per million tokens: (input, output). Public list prices in 2026-10; edit in
# the interface (Configurações > Teto de gastos) when the provider changes them.
PRICES: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {
        "claude-fable-5-1": (10.0, 50.0),
        "claude-opus-5-5": (4.0, 20.0),
        "claude-opus-5": (5.0, 25.0),
        "claude-sonnet-5-5": (2.0, 10.0),
        "claude-sonnet-5": (2.0, 10.0),
        "claude-haiku-5-5": (0.10, 0.50),
    },
    "openai": {
        "gpt-5": (1.25, 10.0),
        "gpt-5-mini": (0.25, 2.0),
        "gpt-5-nano": (0.05, 0.40),
        "gpt-4.1": (2.0, 8.0),
        "gpt-4.1-mini": (0.40, 1.60),
        "text-embedding-3-small": (0.02, 0.0),
        "text-embedding-3-large": (0.13, 0.0),
    },
    "gemini": {
        "gemini-2.5-pro": (1.25, 10.0),
        "gemini-2.5-flash": (0.30, 2.50),
        "gemini-2.5-flash-lite": (0.10, 0.40),
        "gemini-embedding-001": (0.15, 0.0),
    },
}


class BudgetExceeded(Exception):
    """Raised by `check`; llm.py turns it into an AgentUnavailable."""


def is_external(prov: str) -> bool:
    return prov in EXTERNAL


def period_key(settings: dict, ts: float | None = None) -> str:
    if settings.get("spend_period") == "TOTAL":
        return "total"
    return "mes:" + time.strftime("%Y-%m", time.gmtime(ts or time.time()))


def period_label(settings: dict) -> str:
    if settings.get("spend_period") == "TOTAL":
        return "acumulado desde o início"
    return "mês de " + time.strftime("%m/%Y", time.gmtime())


def _match(table: dict[str, tuple[float, float]], model: str) -> tuple[float, float] | None:
    if model in table:
        return table[model]
    # dated or suffixed names (gpt-5-mini-2025-08-07, models/gemini-2.5-flash): longest known prefix
    best = max((k for k in table if model.startswith(k)), key=len, default=None)
    return table[best] if best else None


def price_for(prov: str, model: str, overrides: dict | None = None) -> dict:
    """Price of one model: the override typed in the interface, the built-in table or, when the
    model is unknown, the most expensive model of the provider (so the cap errs on the safe side)."""
    model = (model or "").removeprefix("models/")
    custom = (overrides or {}).get(f"{prov}:{model}")
    if custom:
        return {"entrada": float(custom["entrada"]), "saida": float(custom["saida"]), "origem": "editado"}
    known = _match(PRICES.get(prov, {}), model)
    if known:
        return {"entrada": known[0], "saida": known[1], "origem": "tabela"}
    table = PRICES.get(prov) or {"": (0.0, 0.0)}
    worst = max(table.values(), key=lambda p: p[0] + p[1])
    return {"entrada": worst[0], "saida": worst[1], "origem": "desconhecido"}


def cost(price: dict, tokens_in: int, tokens_out: int) -> float:
    return (tokens_in * price["entrada"] + tokens_out * price["saida"]) / 1_000_000


def estimate_tokens(*texts: str) -> int:
    return sum(len(t or "") for t in texts) // CHARS_PER_TOKEN + 1


def usd(v: float) -> str:
    """Brazilian notation (US$ 1.234,56); four decimals below one dollar."""
    text = f"{v:,.4f}" if 0 < v < 1 else f"{v:,.2f}"
    return "US$ " + text.replace(",", "_").replace(".", ",").replace("_", ".")


class Ledger:
    """Spend counters and the cap check, shared by the API, the workers and the indexer."""

    def __init__(self, store: Store):
        self.store = store

    async def overrides(self) -> dict:
        return await self.store.get_json(PRICES_KEY) or {}

    async def set_price(self, prov: str, model: str, entrada: float | None, saida: float | None) -> dict:
        data = await self.overrides()
        key = f"{prov}:{model}"
        if entrada is None or saida is None:
            data.pop(key, None)
        else:
            if entrada < 0 or saida < 0:
                raise ValueError("o preço não pode ser negativo")
            data[key] = {"entrada": float(entrada), "saida": float(saida)}
        await self.store.set_json(PRICES_KEY, data)
        return data

    async def spent(self, settings: dict) -> float:
        return float(await self.store.r.hget(ACC_KEY, period_key(settings)) or 0)

    async def check(self, settings: dict, prov: str, model: str, est_tokens_in: int = 0, *, mark: bool = True) -> None:
        """Raises BudgetExceeded when the call would start at or above the cap.

        `mark` records the blocking episode (log entry and banner); the wizard's test passes False
        because it checks values that are not saved yet."""
        if not is_external(prov):
            return
        cap = float(settings.get("spend_cap_usd") or 0)
        spent = await self.spent(settings) if cap > 0 else 0.0
        estimate = cost(price_for(prov, model, await self.overrides()), est_tokens_in, 0) if cap > 0 else 0.0
        if cap <= 0 or spent + estimate <= cap:
            # no cap (optional) or room left
            if await self.store.r.exists(BLOCK_KEY):
                await self.store.r.delete(BLOCK_KEY)
            return
        reason = f"teto de gastos atingido: {usd(spent)} gastos de {usd(cap)} ({period_label(settings)})"
        msg = (f"{reason}. Nenhuma chamada nova é feita a {NAMES.get(prov, prov)} até o teto ser aumentado, o período virar "
               "ou o contador ser zerado em Configurações > Teto de gastos.")
        if mark:
            await self._mark_blocked(settings, prov, model, spent, cap, msg)
        raise BudgetExceeded(msg)

    async def _mark_blocked(self, settings: dict, prov: str, model: str, spent: float, cap: float, msg: str) -> None:
        info = {"desde": now_ms(), "provedor": prov, "modelo": model, "gasto_usd": round(spent, 6), "teto_usd": cap,
                "periodo": period_key(settings), "mensagem": msg}
        # first refusal only: one log entry per blocking episode
        if await self.store.r.set(BLOCK_KEY, dumps(info), nx=True):
            logger.warning("chamada externa bloqueada: %s", msg)
            await log.write(self.store, log.GASTOS, f"Chamadas a provedores externos bloqueadas: {msg}", dados=info)
            await self.store.publish({"tipo": "gastos", "bloqueado": True})

    async def charge(self, settings: dict, prov: str, model: str, tokens_in: int | None, tokens_out: int | None, *,
                     origem: str, estimado: bool = False) -> dict:
        """Adds the cost of one finished call to every counter and to the call log."""
        if not is_external(prov):
            return {}
        tin, tout = int(tokens_in or 0), int(tokens_out or 0)
        price = price_for(prov, model, await self.overrides())
        value = cost(price, tin, tout)
        month = "mes:" + time.strftime("%Y-%m", time.gmtime())
        pipe = self.store.r.pipeline()
        for scope in ("total", month):
            pipe.hincrbyfloat(ACC_KEY, scope, value)
            pipe.hincrbyfloat(ACC_KEY, f"{scope}|{prov}|{model}", value)
            pipe.hincrby(ACC_KEY, f"{scope}|chamadas", 1)
        rec = {"ts": now_ms(), "provedor": prov, "modelo": model, "origem": origem, "tokens_entrada": tin, "tokens_saida": tout,
               "custo_usd": round(value, 8), "preco": price, "estimado": estimado}
        pipe.xadd(LOG_KEY, {"d": dumps(rec)}, maxlen=LOG_MAX, approximate=True)
        await pipe.execute()
        spent = await self.spent(settings)
        cap = float(settings.get("spend_cap_usd") or 0)
        alert = float(settings.get("spend_alert_percent") or 0)
        if cap > 0 and alert > 0 and spent - value < cap * alert / 100 <= spent:
            await log.write(self.store, log.GASTOS, f"Gastos com provedores externos passaram de {alert:g}% do teto: "
                            f"{usd(spent)} de {usd(cap)} ({period_label(settings)}).", dados={"gasto_usd": spent, "teto_usd": cap})
        return rec

    async def reset_period(self, settings: dict) -> float:
        """Zeroes the counter of the current period (the call log is kept)."""
        scope = period_key(settings)
        before = await self.spent(settings)
        fields = [f for f in await self.store.r.hkeys(ACC_KEY) if f == scope or f.startswith(scope + "|")]
        if fields:
            await self.store.r.hdel(ACC_KEY, *fields)
        await self.store.r.delete(BLOCK_KEY)
        return before

    async def status(self, settings: dict, recent: int = 0) -> dict[str, Any]:
        scope = period_key(settings)
        acc = await self.store.r.hgetall(ACC_KEY)
        spent = float(acc.get(scope) or 0)
        cap = float(settings.get("spend_cap_usd") or 0)
        by_model = []
        for field, value in acc.items():
            parts = field.split("|")
            if parts[0] == scope and len(parts) == 3:
                by_model.append({"provedor": parts[1], "modelo": parts[2], "custo_usd": round(float(value), 6)})
        by_model.sort(key=lambda m: -m["custo_usd"])
        block = await self.store.get_json(BLOCK_KEY)
        out: dict[str, Any] = {
            "teto_usd": cap, "periodo": settings.get("spend_period") or "MENSAL", "periodo_rotulo": period_label(settings),
            "gasto_usd": round(spent, 6), "gasto_total_usd": round(float(acc.get("total") or 0), 6),
            "restante_usd": round(max(cap - spent, 0), 6), "percentual": round(spent / cap * 100, 1) if cap > 0 else None,
            "chamadas": int(acc.get(f"{scope}|chamadas") or 0), "alerta_percentual": settings.get("spend_alert_percent"),
            "por_modelo": by_model,
            "alerta": cap > 0 and spent >= cap * float(settings.get("spend_alert_percent") or 100) / 100,
        }
        # the cap is optional: without one nothing is ever blocked
        blocked = cap > 0 and spent >= cap
        if not blocked and block:
            await self.store.r.delete(BLOCK_KEY)
            block = None
        if blocked and not block:
            block = {"mensagem": f"teto de gastos atingido: {usd(spent)} gastos de {usd(cap)} ({period_label(settings)})."}
        out.update({"bloqueado": blocked, "bloqueio": block})
        if recent:
            rows = await self.store.r.xrevrange(LOG_KEY, count=recent)
            out["recentes"] = [json.loads(f["d"]) for _, f in rows]
        return out


def price_table(overrides: dict) -> dict[str, list[dict]]:
    """Built-in table merged with the overrides, for the interface."""
    out: dict[str, list[dict]] = {}
    for prov, table in PRICES.items():
        rows = {m: {"modelo": m, "entrada": p[0], "saida": p[1], "origem": "tabela"} for m, p in table.items()}
        for key, val in overrides.items():
            p, _, m = key.partition(":")
            if p == prov:
                rows[m] = {"modelo": m, "entrada": val["entrada"], "saida": val["saida"], "origem": "editado"}
        out[prov] = list(rows.values())
    return out
