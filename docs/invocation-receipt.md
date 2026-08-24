# Router invocation receipt V1

Status: source-owned `contract_only` candidate. It is not an installable Harness
extension and does not authorize a provider call.

`llm-router-invocation-receipt-v1.0` is a privacy-minimized record for values that an
authorized caller has already observed. The builder and codec are offline. They never read
credentials, open a network connection, or retain provider request/response content.

## Contract artifacts

- Python model, semantic validator, and canonical codec:
  [`src/llm_router/receipt.py`](../src/llm_router/receipt.py)
- Generated closed shape schema:
  [`contracts/router-invocation-receipt.v1.schema.json`](../contracts/router-invocation-receipt.v1.schema.json)
- Generator/drift check: `python tools/receipt_contract.py check`

The JSON Schema rejects unknown fields and constrains primitive shapes. The Python
validator is authoritative for the state machine, content identities, and arithmetic.

## Canonical bytes and identities

- UTF-8 JSON, keys sorted, compact separators, no NaN/Infinity, one terminal LF.
- Duplicate keys, unknown fields, noncanonical whitespace, noncanonical timestamps, and
  oversized payloads fail closed.
- `receipt_id` is SHA-256 over the exact canonical body without `receipt_id`, prefixed by
  the domain `llm-router/invocation-receipt/v1\0`.
- `pricing_ref_sha256` separately binds declared pricing source/rates, currency, FX
  source/rate, `half_even` rounding, and caller-supplied pricing/FX source artifact digests.

Hashes are evidence bindings, not signatures or provider attestations.
Every valid receipt fixes `operational_authority=none` and
`invoice_authoritative=false`.

## Attempt and terminal loss accounting

Attempts are contiguous and one-based. Every attempt has one closed outcome and matching
fixed reason code:

| Outcome | HTTP status | Reason code |
|---|---:|---|
| `rate_limited` | 429 | `provider.rate_limited` |
| `server_error` | 500-599 | `provider.server_error` |
| `nonretryable_http_error` | 100-499 except 200/429 | `provider.nonretryable_http_error` |
| `network_error` | absent | `provider.network_error` |
| `invalid_response` | 200 | `provider.invalid_response` |
| `success` | 200 | `provider.success` |

Only retryable outcomes may precede the final attempt. Terminal state must agree with the
final attempt. `missing_configuration` has no attempts; `retry_exhausted` ends in a
retryable outcome; `nonretryable_http_error` ends immediately; `success` and
`empty_content` end in an HTTP success. The receipt response digest must equal the final
attempt response digest. Invalid/nonstandard HTTP status values are reduced to
`invalid_response` without retaining the raw invalid value.

Provider body and exception text are never reason codes. The normal router logger likewise
emits only the fixed public class and HTTP status where applicable.

## Usage and fixed-point money

Token fields are strict nonnegative integers. Provider-reported usage requires
`total_tokens == input_tokens + output_tokens`; absent usage requires all zeros. Failed
invocations cannot claim provider-reported usage.

All cost arithmetic uses integer nano-units:

```text
cost_usd_nanos = half_even(
    (input_tokens * input_rate_usd_nanos_per_million
     + output_tokens * output_rate_usd_nanos_per_million) / 1_000_000
)
```

`illustrative_builtin` and `operator_override` identify the asserted price source and
require `pricing_source_ref_sha256`, a digest of the caller's exact source snapshot.
`unpriced` requires zero rates, zero cost, and no source reference. Operator-declared FX
likewise requires its own source artifact digest; exact USD identity uses a fixed contract
digest; unavailable FX uses `XXX` and zeros. The receipt always states
`invoice_authoritative=false`; source digests do not prove authenticity, and a provider
invoice remains the accounting authority.

## Privacy boundary

Permitted:

- bounded provider and role tokens;
- hashes of model identity, producer, request, response, and output;
- fixed reason codes, HTTP class/status, token counts, rates, and costs.

Forbidden by the closed model:

- credentials, authorization headers, endpoints, or base URLs;
- raw system/user prompts or request payloads;
- raw model output, provider body, or exception text;
- private paths or operational permission.

Model names are hashed because a configured URI or internal model name can contain tenant
or deployment identifiers.

These deterministic digests are content-minimizing, not anonymizing. They are linkable
across receipts and vulnerable to dictionary guessing when the possible source values are
small. A receipt that derives from private prompts, model names, incidents, or customer
data is not automatically public-safe and must remain under the caller's access and
retention policy.

## Honest integration boundary

The existing async `call()` API still returns `(text | None, usage)` and is not silently
changed to produce receipts. A caller may build a receipt only from values it actually
observed. Synthetic conformance tests prove local contract behavior, not provider identity,
invoice accuracy, production safety, or independent effectiveness.
