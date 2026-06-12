# -*- coding: utf-8 -*-
"""Offline budget and savings helpers for llm-router usage records.

The router itself is intentionally stateless. These helpers operate on the usage
dicts returned by ``call()`` so applications can keep their own JSONL budget log
and still compute warnings, caps, and counterfactual savings without adding a
database or background service.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable

from .client import estimate_cost, model_for


class BudgetExceeded(RuntimeError):
    """Raised by ``raise_if_budget_exceeded`` when spend is above the configured cap."""


@dataclass(frozen=True)
class UsageSummary:
    """Aggregate cost and token counts from router usage records."""

    calls: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cost_local: float
    currency: str
    by_role_usd: dict[str, float] = field(default_factory=dict)
    by_model_usd: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "cost_local": round(self.cost_local, 6),
            "currency": self.currency,
            "by_role_usd": {k: round(v, 6) for k, v in sorted(self.by_role_usd.items())},
            "by_model_usd": {k: round(v, 6) for k, v in sorted(self.by_model_usd.items())},
        }


@dataclass(frozen=True)
class BudgetStatus:
    """Budget status for a usage summary."""

    limit_usd: float | None
    spent_usd: float
    remaining_usd: float | None
    usage_ratio: float | None
    warning: bool
    exceeded: bool

    def as_dict(self) -> dict:
        return {
            "limit_usd": self.limit_usd,
            "spent_usd": round(self.spent_usd, 6),
            "remaining_usd": None if self.remaining_usd is None else round(self.remaining_usd, 6),
            "usage_ratio": None if self.usage_ratio is None else round(self.usage_ratio, 3),
            "warning": self.warning,
            "exceeded": self.exceeded,
        }


@dataclass(frozen=True)
class SavingsReport:
    """Counterfactual savings versus sending the same tokens to one model."""

    actual: UsageSummary
    counterfactual_model: str
    counterfactual_cost_usd: float
    saved_usd: float
    savings_rate: float

    def as_dict(self) -> dict:
        return {
            "actual": self.actual.as_dict(),
            "counterfactual_model": self.counterfactual_model,
            "counterfactual_cost_usd": round(self.counterfactual_cost_usd, 6),
            "saved_usd": round(self.saved_usd, 6),
            "savings_rate": round(self.savings_rate, 3),
        }


def _f(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def summarize_usage(usages: Iterable[dict]) -> UsageSummary:
    """Aggregate usage dicts returned by ``call``.

    Unknown or malformed numeric values are treated as zero. This keeps budget
    reporting resilient to provider failures, while the raw usage log remains the
    source for debugging malformed records.
    """

    rows = list(usages)
    by_role: dict[str, float] = {}
    by_model: dict[str, float] = {}
    total_tokens = input_tokens = output_tokens = 0
    cost_usd = cost_local = 0.0
    currency = "USD"

    for row in rows:
        role = str(row.get("role") or "unknown")
        model = str(row.get("model") or "unknown")
        usd = _f(row.get("cost_usd"))
        local = _f(row.get("cost_local"), usd)
        total_tokens += _i(row.get("total_tokens"))
        input_tokens += _i(row.get("input_tokens"))
        output_tokens += _i(row.get("output_tokens"))
        cost_usd += usd
        cost_local += local
        by_role[role] = by_role.get(role, 0.0) + usd
        by_model[model] = by_model.get(model, 0.0) + usd
        if row.get("currency"):
            currency = str(row["currency"])

    return UsageSummary(
        calls=len(rows),
        total_tokens=total_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        cost_local=cost_local,
        currency=currency,
        by_role_usd=by_role,
        by_model_usd=by_model,
    )


def budget_status(
    usages: Iterable[dict],
    *,
    limit_usd: float | None = None,
    warn_at: float = 0.8,
) -> BudgetStatus:
    """Compare usage records to a daily/application budget.

    If ``limit_usd`` is omitted, ``LLM_BUDGET_USD_DAY`` is read from the environment.
    Missing or non-positive limits mean "no cap configured".
    """

    summary = summarize_usage(usages)
    if limit_usd is None:
        raw_limit = os.getenv("LLM_BUDGET_USD_DAY")
        limit_usd = _f(raw_limit, 0.0) if raw_limit else None
    if limit_usd is None or limit_usd <= 0:
        return BudgetStatus(None, summary.cost_usd, None, None, False, False)
    ratio = summary.cost_usd / limit_usd
    return BudgetStatus(
        limit_usd=float(limit_usd),
        spent_usd=summary.cost_usd,
        remaining_usd=max(0.0, float(limit_usd) - summary.cost_usd),
        usage_ratio=ratio,
        warning=ratio >= warn_at,
        exceeded=summary.cost_usd >= limit_usd,
    )


def raise_if_budget_exceeded(usages: Iterable[dict], *, limit_usd: float | None = None) -> None:
    """Raise ``BudgetExceeded`` if spend is at or above the configured cap."""

    status = budget_status(usages, limit_usd=limit_usd)
    if status.exceeded:
        raise BudgetExceeded(
            f"LLM budget exceeded: spent ${status.spent_usd:.6f} "
            f"of ${status.limit_usd:.6f}"
        )


def build_savings_report(
    usages: Iterable[dict],
    *,
    counterfactual_role: str = "chief",
    counterfactual_model: str | None = None,
    provider: str | None = None,
) -> SavingsReport:
    """Estimate savings versus routing all observed tokens through one model.

    The estimate uses the same input/output token counts from the usage records and prices
    them against ``counterfactual_model`` (or the model configured for
    ``counterfactual_role``). It does not predict different output lengths.
    """

    rows = list(usages)
    actual = summarize_usage(rows)
    model = counterfactual_model or model_for(counterfactual_role, provider)
    counterfactual = sum(
        estimate_cost(model, _i(row.get("input_tokens")), _i(row.get("output_tokens")))
        for row in rows
    )
    saved = max(0.0, counterfactual - actual.cost_usd)
    rate = saved / counterfactual if counterfactual > 0 else 0.0
    return SavingsReport(
        actual=actual,
        counterfactual_model=model,
        counterfactual_cost_usd=counterfactual,
        saved_usd=saved,
        savings_rate=rate,
    )
