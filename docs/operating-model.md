# Operating Model

`llm-router` is a small client, not an LLM gateway. It helps an application route
calls by role and record per-call usage. The application still owns policy,
storage, rate limits, audit, and approval.

Portfolio role: support library. The portfolio-level source-of-truth and
public/private documentation hierarchy live in the
[Documentation Contract](https://github.com/krivonosoff161/krivonosoff161/blob/main/docs/documentation-contract.md).

## Source Baseline

The operating model follows a few public ideas:

- keep agent actions observable and bounded:
  <https://developers.openai.com/api/docs/guides/agent-builder-safety>
- track generative-AI risks, measurement limits, and monitoring as ongoing
  practice:
  <https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf>
- treat LLM application behavior as a security surface, including excessive
  agency, supply-chain risk, and sensitive information disclosure:
  <https://owasp.org/www-project-top-10-for-large-language-model-applications/>

These references do not turn this package into a compliance control. They are
the reason the router keeps role, model, provider, token, and cost data visible.

## Role Budget Model

| Role | Typical use | Budget expectation | Promotion rule |
|---|---|---|---|
| `cheap` | extraction, rough classification, first-pass filtering, summaries | high call count, low cost per call | promote only if deterministic filters or confidence rules say the item matters |
| `mid` | second-pass classification, enrichment, uncertainty resolution | moderate call count | promote when the output affects a user-visible or expensive action |
| `chief` | final decision, high-impact answer, user-facing recommendation | low call count, higher cost | use only after cheaper stages narrow the candidate set |
| `audit` | independent check, replay, disagreement review, safety review | sparse and intentional | use when the decision needs a second model or different provider perspective |

The router does not enforce these rules. It returns enough data for the caller to
enforce them.

## Usage Record Contract

Every `call(...)` returns a usage dict shaped for JSONL logging:

| Field | Why it matters |
|---|---|
| `provider` | shows which service handled the request |
| `model` | ties spend and behavior to a concrete configured model |
| `role` | lets reports show cheap/mid/chief/audit distribution |
| `input_tokens`, `output_tokens`, `total_tokens` | supports volume and anomaly checks |
| `cost_usd`, `cost_local`, `currency` | supports daily budget reports and local accounting |

Recommended caller-owned fields:

- `run_id`
- `request_id`
- `task_type`
- `decision_id`
- `timestamp`
- `success`
- `error_class`
- `escalated_from`
- `approved_by` when a human gate was required

Keep raw prompts and model responses in a separate private log if they can
contain secrets, customer data, private code, or provider configuration.

## Budget Checks

Use the offline helpers against the JSONL records you own:

```python
from llm_router import budget_status, build_savings_report, summarize_usage

summary = summarize_usage(usages)
status = budget_status(usages, limit_usd=5.00)
savings = build_savings_report(usages, counterfactual_role="chief")
```

Useful gates:

- warn at 80 percent of a daily budget;
- block or require approval at 100 percent;
- alert if `chief` calls exceed an expected ratio;
- alert if a cheap-stage batch suddenly produces much larger outputs;
- compare actual routed cost with a chief-only counterfactual before changing
  routing policy.

## Failure Modes

- A caller ignores `text is None` and treats a failed call as a negative result.
- The built-in price table is used as if it were an invoice.
- A cheap role is quietly configured to an expensive model.
- A chief role is overused because promotion rules are too loose.
- Provider errors are retried locally, but there is no global rate-limit budget
  across concurrent workers.
- A usage log is public even though prompts, task names, or model names reveal
  private workflow details.
- The router is treated as a policy gateway even though it only performs calls
  and returns usage data.

## When This Is Not Enough

Use a full gateway or policy layer when you need:

- centralized secrets management;
- organization-wide rate limits;
- prompt/response storage and redaction;
- tool-call approval;
- multi-tenant access control;
- provider failover with health checks;
- audit retention policies;
- security event monitoring.

`llm-router` can sit inside that architecture, but it is not that architecture.
