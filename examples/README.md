# Examples

Both examples make **real API calls** — set a provider + key first (see
[.env.example](../.env.example)). Without a key they exit gracefully with an
`API key not set` warning and a zeroed usage dict, so running them "empty" is
safe.

```bash
export OPENAI_API_KEY=sk-...      # or the Yandex pair — see README "Providers"
python examples/basic.py
python examples/role_tiers.py
```

| Example | Shows | Expected output |
|---|---|---|
| `basic.py` | one `call("cheap", ...)` and the shape of the usage dict | the model reply + a dict with `provider/model/role/tokens/cost_usd/cost_local/currency` |
| `role_tiers.py` | the same question asked on the `cheap` and `chief` tiers | per-tier model name, reply, and cost — the cost gap between tiers is the point |

**The lesson:** routing by role is one line at the call site; the cost
difference you see in `role_tiers.py` is what you save on every bulk call you
keep on the cheap tier.

**What these examples do NOT prove:** that the cheap tier is *good enough* for
your task — that's a quality judgment you make per use case (see the sibling
[llm-cheap-filter](https://github.com/krivonosoff161/llm-cheap-filter) for an
escalation pattern when cheap isn't sure).

For offline behavior (retries, error paths, cost accounting) read the tests —
they run without any network: `python -m pytest -q`.
