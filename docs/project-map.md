# Project map — for reviewers and maintainers

A plain-language guide to what this repository contains, how to inspect it
quickly, and how to change it safely.

## What it does

`llm-router` is a single-file async client that routes an LLM call to a model
chosen by **role** (`cheap` / `mid` / `chief` / `audit`), across any
OpenAI-compatible endpoint or Yandex AI Studio, and returns the text together
with a **usage dict** (tokens + cost in USD and a configurable local currency).

In the public portfolio this is a support layer, not a flagship project. The
portfolio-level documentation hierarchy is defined in the
[Documentation Contract](https://github.com/krivonosoff161/krivonosoff161/blob/main/docs/documentation-contract.md).

The mental model is one sentence: *"send bulk work to the cheap tier, escalate
the few decisions that matter to the chief tier, and know what every call
cost you."*

## Pipeline

```
call(role, system, user)
  ├─ active_provider()      env: LLM_PROVIDER         -> "openai" | "yandex"
  ├─ model_for(role)        env: LLM_<ROLE>_MODEL ... -> model name (fail-fast for Yandex)
  ├─ _build_request()       env: keys + base URLs     -> (url, headers, payload) | (None,)*3
  ├─ aiohttp POST           retries on 429/5xx, exponential backoff (cap 8 s)
  └─ usage_dict()           env: LLM_FX / LLM_CCY / price overrides -> tokens + cost
```

## Key modules

| File | Role | Size |
|---|---|---|
| `src/llm_router/client.py` | everything: provider resolution, request building, retry loop, cost accounting | ~170 lines |
| `src/llm_router/budget.py` | offline usage aggregation, budget status, and counterfactual savings helpers | ~220 lines |
| `src/llm_router/receipt.py` | closed canonical invocation receipt, attempt state machine, fixed-point arithmetic | bounded |
| `contracts/router-invocation-receipt.v1.schema.json` | generated closed shape schema; Python owns semantic checks | generated |
| `src/llm_router/__init__.py` | public exports for client, budget, and receipt helpers | small |
| `tests/test_client.py` | 20 offline tests — helpers **and** the full `call()` path with a mocked `aiohttp` session | ~250 lines |
| `tests/test_budget.py` | offline tests for usage summary, budget caps, and savings estimates | small |
| `examples/` | two runnable scripts (need a real API key) — see [examples/README.md](../examples/README.md) | small |
| `docs/operating-model.md` | role-budget operating model, usage-log fields, escalation gates, and residual risk | small |

There is intentionally no package layering: one file is the whole surface.

## What exists today

- One async `call()` for chat completions (one system + one user message).
- Two provider paths: OpenAI-compatible (Bearer) and Yandex AI Studio (Api-Key).
- Role→model mapping, JSON mode, per-call cost with env-overridable prices.
- Offline budget helpers for usage logs: `summarize_usage`, `budget_status`,
  `raise_if_budget_exceeded`, and `build_savings_report`.
- Retry on 429/5xx, timeout, fail-fast on missing Yandex config.
- Errors are reported via the `llm_router` logger (no exceptions leak to the caller;
  failures return `(None, usage)`). Provider body and exception text are not logged;
  fixed reason codes preserve the public diagnostic class.
- Source-owned canonical invocation receipt V1 for already-observed sanitized attempt,
  token, pricing, and FX evidence. It does not call providers.

## What is NOT included (by design)

- Streaming, embeddings, tools/function calling, vision, multi-turn history.
- Provider SDKs, connection pooling across calls, runtime global rate-limit budgeting.
- Any persistence — the caller decides what to do with the usage dicts.

If a change adds one of these, it is a scope change, not a fix — discuss first.

## How to inspect without reading every line

1. Read `client.py` top docstring (the contract) — 25 lines.
2. Read `call()` (the last function) — the entire runtime behavior is there.
3. Skim `tests/test_client.py` test names — they enumerate the supported behaviors.
4. Skim `budget.py` — it has no network calls and only operates on returned usage dicts.

## How to run checks

```bash
python -m pytest -q        # 20 offline tests, no network, < 1 s
python -m ruff check .     # lint
python tools/receipt_contract.py check
python examples/basic.py   # smoke (requires a provider key; prints a clear
                           # "API key not set" warning otherwise)
```

CI (`.github/workflows/tests.yml`) runs pytest on Python 3.9 / 3.11 / 3.12 / 3.13
across Linux and Windows.

## How to extend safely

- New OpenAI-compatible provider: **no code** — set `OPENAI_BASE_URL` + key.
- New role tier: add it to `_OPENAI_DEFAULTS` / `_OPENAI_ENV` / `_YANDEX_DEFAULTS`;
  add a `model_for` test.
- New native provider (non-OpenAI wire format): add a branch in `_build_request`
  and a parsing branch in `call()`; add request-building tests **and** a mocked
  `call()` test. Keep the `(text | None, usage)` return contract intact.
- Price table updates: prefer documenting the env override; the built-in table
  is illustrative, not authoritative.
- Budget logic: keep it offline/stateless unless the repository intentionally grows a
  persistence layer. The caller owns the JSONL log.

## Reviewer checklist (for future changes, incl. agent-generated)

- [ ] `(text | None, usage)` contract unchanged; `usage` keys unchanged.
- [ ] No secret read at import time; all env reads stay inside functions.
- [ ] No new runtime dependency beyond `aiohttp` without explicit discussion.
- [ ] Every new behavior has an offline test (mock the session, never the network).
- [ ] README tables (providers / env vars) still match the code.
- [ ] No claim of provider coverage beyond what `_build_request` actually handles.
- [ ] Budget helpers still make clear they estimate from usage records, not invoices.
- [ ] Receipt changes preserve closed fields, canonical bytes, domain identity, attempt
      loss accounting, fixed-point arithmetic, and the raw-data exclusion boundary.
