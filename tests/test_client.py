# -*- coding: utf-8 -*-
"""Offline unit tests for llm_router (no network calls)."""
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from llm_router import client  # noqa: E402
from llm_router import estimate_cost, model_for, usage_dict  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip all llm_router env vars before each test for isolation."""
    for k in list(__import__("os").environ):
        if k.startswith(("LLM_", "OPENAI_", "YANDEX_")):
            monkeypatch.delenv(k, raising=False)


def test_model_for_openai_defaults():
    assert model_for("cheap", "openai") == "gpt-4o-mini"
    assert model_for("chief", "openai") == "gpt-4o"


def test_model_for_env_override(monkeypatch):
    monkeypatch.setenv("LLM_CHEAP_MODEL", "qwen3-30b-a3b-instruct-2507")
    assert model_for("cheap", "openai") == "qwen3-30b-a3b-instruct-2507"


def test_model_for_yandex_wraps_folder(monkeypatch):
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder123")
    assert model_for("chief", "yandex") == "gpt://folder123/yandexgpt/latest"


def test_model_for_yandex_raises_without_config():
    # fail fast: no YANDEX_FOLDER_ID and no explicit YANDEX_<ROLE>_MODEL
    with pytest.raises(ValueError):
        model_for("chief", "yandex")


def test_estimate_cost_known_model():
    # gpt-4o-mini = (0.15, 0.60) USD / 1M
    cost = estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.75)


def test_estimate_cost_env_override(monkeypatch):
    monkeypatch.setenv("LLM_PRICE_GPT_4O_MINI_IN_USD_PER_1M", "1.0")
    monkeypatch.setenv("LLM_PRICE_GPT_4O_MINI_OUT_USD_PER_1M", "2.0")
    assert estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000) == pytest.approx(3.0)


def test_usage_dict_tokens_and_local_currency(monkeypatch):
    monkeypatch.setenv("LLM_FX", "90")
    monkeypatch.setenv("LLM_CCY", "RUB")
    fake = {"usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    u = usage_dict("openai", "gpt-4o-mini", "cheap", fake)
    assert u["input_tokens"] == 100 and u["output_tokens"] == 50 and u["total_tokens"] == 150
    assert u["currency"] == "RUB"
    assert u["cost_local"] == pytest.approx(u["cost_usd"] * 90)


def test_build_request_openai_bearer(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    url, headers, payload = client._build_request("openai", "gpt-4o", "sys", "usr", False, 100)
    assert url.endswith("/chat/completions")
    assert headers["Authorization"] == "Bearer sk-test"
    assert payload["messages"][0]["role"] == "system"
    assert "response_format" not in payload


def test_build_request_json_mode_adds_response_format(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _, _, payload = client._build_request("openai", "gpt-4o", "sys", "usr", True, 100)
    assert payload["response_format"] == {"type": "json_object"}


def test_build_request_custom_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/compatible-mode/v1/")
    url, _, _ = client._build_request("openai", "m", "s", "u", False, 100)
    assert url == "https://example.com/compatible-mode/v1/chat/completions"


def test_build_request_yandex_apikey(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "ya-test")
    url, headers, _ = client._build_request("yandex", "gpt://f/m/latest", "s", "u", False, 100)
    assert headers["Authorization"] == "Api-Key ya-test"


def test_build_request_missing_key_returns_none():
    assert client._build_request("openai", "m", "s", "u", False, 100) == (None, None, None)
