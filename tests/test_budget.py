# -*- coding: utf-8 -*-
"""Offline tests for budget and savings helpers."""

import pytest

from llm_router import (
    BudgetExceeded,
    budget_status,
    build_savings_report,
    raise_if_budget_exceeded,
    summarize_usage,
)


def _usage(role: str, model: str, inp: int, out: int, cost: float) -> dict:
    return {
        "provider": "openai",
        "model": model,
        "role": role,
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "cost_usd": cost,
        "cost_local": cost * 100,
        "currency": "RUB",
    }


def test_summarize_usage_groups_by_role_and_model() -> None:
    rows = [
        _usage("cheap", "gpt-4o-mini", 100, 20, 0.001),
        _usage("chief", "gpt-4o", 200, 50, 0.02),
        _usage("cheap", "gpt-4o-mini", 30, 10, 0.0005),
    ]

    summary = summarize_usage(rows)

    assert summary.calls == 3
    assert summary.total_tokens == 410
    assert summary.input_tokens == 330
    assert summary.output_tokens == 80
    assert summary.cost_usd == pytest.approx(0.0215)
    assert summary.cost_local == pytest.approx(2.15)
    assert summary.currency == "RUB"
    assert summary.as_dict()["by_role_usd"] == {"cheap": 0.0015, "chief": 0.02}
    assert summary.as_dict()["by_model_usd"] == {"gpt-4o": 0.02, "gpt-4o-mini": 0.0015}


def test_budget_status_uses_explicit_limit() -> None:
    rows = [_usage("cheap", "gpt-4o-mini", 100, 10, 0.04)]

    status = budget_status(rows, limit_usd=0.05, warn_at=0.75)

    assert status.warning is True
    assert status.exceeded is False
    assert status.as_dict()["usage_ratio"] == 0.8
    assert status.as_dict()["remaining_usd"] == 0.01


def test_budget_status_reads_env_limit(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BUDGET_USD_DAY", "0.03")

    status = budget_status([_usage("chief", "gpt-4o", 100, 10, 0.03)])

    assert status.exceeded is True
    assert status.remaining_usd == 0.0


def test_budget_status_without_limit_is_unconfigured() -> None:
    status = budget_status([_usage("cheap", "gpt-4o-mini", 1, 1, 1.0)])

    assert status.limit_usd is None
    assert status.warning is False
    assert status.exceeded is False


def test_raise_if_budget_exceeded() -> None:
    rows = [_usage("chief", "gpt-4o", 100, 10, 0.11)]

    with pytest.raises(BudgetExceeded):
        raise_if_budget_exceeded(rows, limit_usd=0.10)


def test_build_savings_report_prices_same_tokens_on_counterfactual_model() -> None:
    rows = [
        _usage("cheap", "gpt-4o-mini", 1_000_000, 0, 0.15),
        _usage("mid", "gpt-4o-mini", 0, 1_000_000, 0.60),
    ]

    report = build_savings_report(rows, counterfactual_model="gpt-4o")

    # gpt-4o: 1M input at 2.50 + 1M output at 10.00.
    assert report.counterfactual_cost_usd == pytest.approx(12.5)
    assert report.actual.cost_usd == pytest.approx(0.75)
    assert report.saved_usd == pytest.approx(11.75)
    assert report.as_dict()["savings_rate"] == 0.94


def test_summarize_usage_tolerates_malformed_numbers() -> None:
    summary = summarize_usage([{"role": "cheap", "model": "m", "cost_usd": "bad"}])

    assert summary.calls == 1
    assert summary.total_tokens == 0
    assert summary.cost_usd == 0.0
