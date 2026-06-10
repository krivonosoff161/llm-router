# Use cases

## Who this is for

Developers building **agentic or batch LLM pipelines** — scanners, classifiers,
extractors, triage bots — who want to control model spend without adopting a
framework or juggling provider SDKs.

## The problem it solves

In most agent loops 80–95 % of LLM calls are bulk work (extract facts, classify,
summarize) and a handful are high-stakes decisions. Paying flagship prices for
everything multiplies the bill; hard-coding one provider makes switching painful;
and without per-call cost data you discover overspend only on the invoice.

`llm-router` addresses exactly those three points: role tiers, provider
flexibility via env, and a cost-stamped usage dict on every call.

## Practical workflows

**1. Cheap→chief escalation in a scanner.**
A news/alert pipeline calls `call("cheap", EXTRACT, text)` on every item and
only escalates promising candidates with `call("chief", DECIDE, facts,
json_mode=True)`. (This is the pattern the sibling
[llm-cheap-filter](https://github.com/krivonosoff161/llm-cheap-filter)
packages as a pipeline; llm-router is the client underneath.)

**2. Budget log with zero infrastructure.**
Append every returned `usage` dict to a JSONL file. You get per-call
provider/model/tokens/cost in USD and your local currency — enough for a daily
spend report with `jq` or ten lines of Python.

**3. Provider migration without code changes.**
Moving bulk traffic from OpenAI to a cheaper OpenAI-compatible host (Alibaba,
OpenRouter, Together, local Ollama/vLLM) is an env edit: `OPENAI_BASE_URL` +
key + model names. The decision tier can stay where it is.

**4. Regional/provider redundancy.**
Keep a Yandex AI Studio configuration next to an OpenAI-compatible one and flip
`LLM_PROVIDER` per environment — useful when one provider is unavailable in a
deployment region.

## What this is not

- **Not a framework** — no chains, no memory, no tool calling. It is the thin
  client you call from your own loop.
- **Not an SDK wrapper** — it speaks the HTTP wire format directly.
- **Not a guarantee of price accuracy** — the built-in price table is
  illustrative; override it with your provider's real prices.

## Limitations and residual risk

- Chat completions only; one system + one user message per call.
- Failures return `(None, usage)` rather than raising — callers must check for
  `None` or items will be silently skipped.
- Retries (429/5xx) are basic exponential backoff; there is no global rate-limit
  budget across concurrent callers.
- Cost figures are estimates from token counts × configured prices — they will
  not match invoices that bill cached/batch tokens differently.
- CI covers Linux (3.9/3.11/3.12); Windows is used in development but not in CI.
