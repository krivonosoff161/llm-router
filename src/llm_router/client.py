# -*- coding: utf-8 -*-
"""
llm_router — cost-aware multi-provider LLM router with role tiers.

A tiny (single-file) async client that gives you ONE `call()` interface across:
  * any OpenAI-compatible endpoint (OpenAI, Alibaba Qwen, OpenRouter, Together,
    local Ollama / vLLM, ...) — set OPENAI_BASE_URL + OPENAI_API_KEY
  * Yandex AI Studio (native) — set YANDEX_API_KEY + YANDEX_FOLDER_ID

Why: in agentic systems you want to send high-volume work to a CHEAP model and
reserve an EXPENSIVE one for the few high-stakes decisions. This router maps four
roles (cheap / mid / chief / audit) to models via environment variables, retries
on 429/5xx with exponential backoff, and returns a usage dict with token counts
and the per-call cost (USD + a configurable local currency).

No SDKs, no models hardcoded in the logic — just aiohttp + env config.

    text, usage = await call("cheap", "You are concise.", "Say hi in 3 words.")
    # usage = {provider, model, role, input_tokens, output_tokens, total_tokens,
    #          cost_usd, cost_local, currency}

All configuration is read live from the environment, so tests and runtime can
change it without re-importing, and no secret is cached at import time.
"""
from __future__ import annotations

import asyncio
import os

import aiohttp

# Default model per role for OpenAI-compatible providers (override via env).
_OPENAI_DEFAULTS = {"cheap": "gpt-4o-mini", "mid": "gpt-4o-mini",
                    "chief": "gpt-4o", "audit": "gpt-4o"}
_OPENAI_ENV = {"cheap": "LLM_CHEAP_MODEL", "mid": "LLM_MID_MODEL",
               "chief": "LLM_CHIEF_MODEL", "audit": "LLM_AUDIT_MODEL"}
# Default Yandex model names per role (wrapped into gpt://<folder>/<name>/latest).
_YANDEX_DEFAULTS = {"cheap": "yandexgpt-lite", "mid": "yandexgpt",
                    "chief": "yandexgpt", "audit": "yandexgpt"}

# Illustrative list prices (USD per 1M tokens: input, output). ALWAYS confirm
# against your provider; override per model via env (see estimate_cost).
_PRICE_USD_PER_1M = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "qwen3-30b-a3b-instruct-2507": (0.20, 0.80),
    "qwen3-235b-a22b-instruct-2507": (0.23, 0.92),
}


def active_provider(provider: str | None = None) -> str:
    return (provider or os.getenv("LLM_PROVIDER", "openai")).strip().lower()


def model_for(role: str, provider: str | None = None) -> str:
    """Resolve a role (cheap/mid/chief/audit) to its configured model (env-driven).

    Raises ValueError for a misconfigured Yandex provider (no YANDEX_FOLDER_ID and
    no explicit YANDEX_<ROLE>_MODEL) — fail fast instead of sending an empty model.
    """
    p = active_provider(provider)
    if p == "yandex":
        uri = os.getenv(f"YANDEX_{role.upper()}_MODEL", "").strip("'\"")
        if uri:
            return uri
        folder = os.getenv("YANDEX_FOLDER_ID", "").strip()
        if not folder:
            raise ValueError(
                f"llm_router: Yandex model for role '{role}' is not configured — "
                f"set YANDEX_FOLDER_ID or YANDEX_{role.upper()}_MODEL"
            )
        name = _YANDEX_DEFAULTS.get(role, "yandexgpt")
        return f"gpt://{folder}/{name}/latest"
    env_key = _OPENAI_ENV.get(role)
    return os.getenv(env_key, _OPENAI_DEFAULTS.get(role, "gpt-4o")) if env_key else "gpt-4o"


def estimate_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    """USD cost for a call from the price table (override per model via env)."""
    key = model.upper().replace("-", "_").replace(".", "_").replace("/", "_")
    in_rate, out_rate = _PRICE_USD_PER_1M.get(model, (0.0, 0.0))
    in_rate = float(os.getenv(f"LLM_PRICE_{key}_IN_USD_PER_1M", in_rate))
    out_rate = float(os.getenv(f"LLM_PRICE_{key}_OUT_USD_PER_1M", out_rate))
    return in_tokens / 1_000_000 * in_rate + out_tokens / 1_000_000 * out_rate


def usage_dict(provider: str, model: str, role: str, data: dict | None) -> dict:
    """Build the usage record (tokens + cost) from a provider response."""
    u = (data or {}).get("usage", {}) or {}
    inp = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
    out = int(u.get("completion_tokens") or u.get("output_tokens") or 0)
    total = int(u.get("total_tokens") or (inp + out))
    cost_usd = estimate_cost(model, inp, out)
    fx = float(os.getenv("LLM_FX", "1.0"))            # USD → local currency multiplier
    ccy = os.getenv("LLM_CCY", "USD").strip()         # local currency label
    return {"provider": provider, "model": model, "role": role,
            "input_tokens": inp, "output_tokens": out, "total_tokens": total,
            "cost_usd": round(cost_usd, 6),
            "cost_local": round(cost_usd * fx, 6), "currency": ccy}


def _build_request(provider: str, model: str, system: str, user: str,
                   json_mode: bool, max_tokens: int):
    """Return (url, headers, payload) for the active provider, or (None,)*3 if no key."""
    payload = {"model": model, "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    if provider == "yandex":
        key = os.getenv("YANDEX_API_KEY", "").strip("'\"")
        if not key:
            return None, None, None
        base = os.getenv("YANDEX_BASE_URL", "https://ai.api.cloud.yandex.net/v1").rstrip("/")
        return base + "/chat/completions", {"Authorization": f"Api-Key {key}",
                                            "Content-Type": "application/json"}, payload
    # OpenAI-compatible (OpenAI / Alibaba / OpenRouter / Together / Ollama / ...)
    key = os.getenv("OPENAI_API_KEY", "").strip("'\"")
    if not key:
        return None, None, None
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if json_mode:
        payload["response_format"] = {"type": "json_object"}   # include the word JSON in your prompt
    return base + "/chat/completions", {"Authorization": f"Bearer {key}",
                                        "Content-Type": "application/json"}, payload


async def call(role: str, system: str, user: str, *,
               json_mode: bool = False, max_tokens: int = 900,
               timeout: int | None = None, provider: str | None = None
               ) -> tuple[str | None, dict]:
    """Call the model for `role` on the active provider.

    Returns (text|None, usage). Retries on 429/5xx with exponential backoff.
    """
    p = active_provider(provider)
    model = model_for(role, p)
    timeout = timeout or int(os.getenv("LLM_DEFAULT_TIMEOUT", "60"))
    retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
    url, headers, payload = _build_request(p, model, system, user, json_mode, max_tokens)
    if url is None:
        print(f"llm_router[{p}/{role}]: API key not set")
        return None, usage_dict(p, model, role, {})

    last_err = None
    for attempt in range(retries + 1):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=payload, headers=headers,
                                  timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                    if r.status == 429 or r.status >= 500:
                        last_err = f"HTTP {r.status}"
                        await asyncio.sleep(min(2 ** attempt, 8))
                        continue
                    if r.status != 200:
                        body = await r.text()
                        print(f"llm_router[{p}/{role}]: HTTP {r.status} — {body[:200]}")
                        return None, usage_dict(p, model, role, {})
                    data = await r.json()
            text = (data["choices"][0]["message"]["content"] or "").strip()
            return (text or None), usage_dict(p, model, role, data)
        except Exception as e:  # noqa: BLE001 — network/parse errors are retried
            last_err = str(e)
            await asyncio.sleep(min(2 ** attempt, 8))
    print(f"llm_router[{p}/{role}]: failed after retries — {last_err}")
    return None, usage_dict(p, model, role, {})
