# -*- coding: utf-8 -*-
"""llm_router - cost-aware multi-provider LLM router with role tiers."""

from .budget import (
    BudgetExceeded,
    BudgetStatus,
    SavingsReport,
    UsageSummary,
    budget_status,
    build_savings_report,
    raise_if_budget_exceeded,
    summarize_usage,
)
from .client import (
    active_provider,
    call,
    estimate_cost,
    model_for,
    usage_dict,
)

__all__ = [
    "call",
    "model_for",
    "estimate_cost",
    "usage_dict",
    "active_provider",
    "UsageSummary",
    "BudgetStatus",
    "SavingsReport",
    "BudgetExceeded",
    "summarize_usage",
    "budget_status",
    "raise_if_budget_exceeded",
    "build_savings_report",
]
__version__ = "0.1.0"
