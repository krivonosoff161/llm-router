# llm-router

[![Tests](https://github.com/krivonosoff161/llm-router/actions/workflows/tests.yml/badge.svg)](https://github.com/krivonosoff161/llm-router/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

**A tiny, dependency-light async LLM router with role tiers and per-call cost logging.**
One `call()` interface across any OpenAI-compatible endpoint (OpenAI, Alibaba Qwen, OpenRouter, Together, local Ollama/vLLM) **and** Yandex AI Studio — so you send high-volume work to a *cheap* model and reserve an *expensive* one for the few decisions that matter.

> Extracted and generalized from a production agentic news scanner that runs nightly on a cheap→chief tier. No SDKs, no models hardcoded in the logic — just `aiohttp` + environment config.

---

## Why

In agentic systems most LLM calls are cheap bulk work (extract, classify, filter) and a few are high-stakes (the final decision). Paying flagship prices for everything is wasteful; juggling provider SDKs is annoying. `llm-router` gives you:

- **Role tiers** — `cheap` / `mid` / `chief` / `audit`, each mapped to a model via env. Route volume to `cheap`, escalate only candidates to `chief`.
- **Provider flexibility** — one env var flips between OpenAI-compatible providers; a custom `OPENAI_BASE_URL` covers Alibaba, OpenRouter, Together, Ollama, vLLM, etc. Yandex AI Studio has a native path.
- **Per-call cost** — every call returns token counts and cost in **USD + a configurable local currency** (set `LLM_FX` / `LLM_CCY`). Aggregate the dicts to a budget log.
- **Resilience** — retries on `429` / `5xx` with exponential backoff.

---

## Features

- Single `async call(role, system, user) -> (text | None, usage)` interface.
- Four configurable role tiers, models set per provider via env.
- OpenAI-compatible **and** Yandex AI Studio providers.
- `json_mode=True` → adds `response_format={"type":"json_object"}` (OpenAI-compatible).
- Cost estimation from an override-able price table (`LLM_PRICE_<MODEL>_IN/OUT_USD_PER_1M`).
- Zero secrets cached at import — all config read live from env.
- ~150 LOC, one runtime dependency (`aiohttp`).

---

## Install

```bash
git clone https://github.com/krivonosoff161/llm-router
cd llm-router
pip install -e .          # or: pip install -r requirements.txt
```

Requires **Python 3.9+**. Verified on Windows; should run on Linux/macOS (pure Python + `aiohttp`, no OS-specific calls).

---

## Quickstart

```python
import asyncio
from llm_router import call

async def main():
    text, usage = await call("cheap", "You are concise.", "Name 3 primary colors.")
    print(text)
    print(usage)   # {provider, model, role, input_tokens, output_tokens,
                   #  total_tokens, cost_usd, cost_local, currency}

asyncio.run(main())
```

Set at least a provider + key first (see **Configuration**). For OpenAI:

```bash
export OPENAI_API_KEY=sk-...
```

---

## Providers

| Provider | Set | Auth |
|---|---|---|
| **OpenAI** | `LLM_PROVIDER=openai` (default), `OPENAI_API_KEY` | `Bearer` |
| **Alibaba Qwen** | `OPENAI_BASE_URL=<dashscope compatible-mode/v1>` + `OPENAI_API_KEY` | `Bearer` |
| **OpenRouter / Together / Ollama / vLLM** | `OPENAI_BASE_URL=<their /v1>` + `OPENAI_API_KEY` | `Bearer` |
| **Yandex AI Studio** | `LLM_PROVIDER=yandex`, `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` | `Api-Key` |

> The base URL must NOT include `/chat/completions` — the router appends it.
> **Yandex** requires `YANDEX_FOLDER_ID` (or an explicit `YANDEX_<ROLE>_MODEL`); otherwise `model_for` raises a clear configuration error (fail-fast) instead of sending an empty model.

---

## Roles

```python
from llm_router import call, model_for

model_for("cheap")   # -> e.g. "gpt-4o-mini" (or your LLM_CHEAP_MODEL)
model_for("chief")   # -> e.g. "gpt-4o"

# pattern: cheap for volume, chief only when it matters
facts, u1 = await call("cheap", EXTRACT_PROMPT, raw_text)
if looks_important(facts):
    verdict, u2 = await call("chief", DECIDE_PROMPT, facts, json_mode=True)
```

---

## Cost logging

```python
text, usage = await call("cheap", sys, user)
# usage["cost_usd"]   -> e.g. 0.0001
# usage["cost_local"] -> cost_usd * LLM_FX
# usage["currency"]   -> LLM_CCY (e.g. "RUB")
```

Append each `usage` to a JSONL file and you have a per-call budget log. Prices come from a small built-in table and are **illustrative** — override per model:

```bash
export LLM_PRICE_GPT_4O_MINI_IN_USD_PER_1M=0.15
export LLM_PRICE_GPT_4O_MINI_OUT_USD_PER_1M=0.60
```

---

## Configuration (env)

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` (compatible) or `yandex` |
| `OPENAI_API_KEY` | — | key for the OpenAI-compatible endpoint |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | point at Alibaba/OpenRouter/Ollama/... |
| `LLM_CHEAP_MODEL` / `LLM_MID_MODEL` / `LLM_CHIEF_MODEL` / `LLM_AUDIT_MODEL` | gpt-4o-mini / gpt-4o-mini / gpt-4o / gpt-4o | role → model |
| `YANDEX_API_KEY`, `YANDEX_FOLDER_ID` | — | Yandex AI Studio |
| `YANDEX_<ROLE>_MODEL` | wraps `gpt://<folder>/<name>/latest` | override a Yandex role model URI |
| `LLM_FX` | `1.0` | USD → local currency multiplier |
| `LLM_CCY` | `USD` | local currency label |
| `LLM_DEFAULT_TIMEOUT` | `60` | per-call timeout (s) |
| `LLM_MAX_RETRIES` | `2` | retries on 429/5xx |
| `LLM_PRICE_<MODEL>_IN/OUT_USD_PER_1M` | from table | override price per model |

See [.env.example](.env.example).

---

## Examples & tests

```bash
python examples/basic.py          # one call
python examples/role_tiers.py     # cheap vs chief + cost
python -m pytest -q               # offline unit tests (no network)
```

---

## Limitations / non-goals

- Chat completions only (no streaming, embeddings, tools/function-calling, vision — kept intentionally small).
- One system + one user message per call (no multi-turn history helper).
- The price table is illustrative; confirm real prices with your provider.
- Not a full framework — it's a focused routing + cost-logging utility you drop into your own agent loop.

---

## License

MIT — see [LICENSE](LICENSE).
