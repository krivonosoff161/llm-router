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


# ── async call(): mocked aiohttp, no network ─────────────────────────────────
import asyncio  # noqa: E402


class _FakeResponse:
    """Async-context response with canned status/json/text."""

    def __init__(self, status=200, data=None, text=""):
        self.status = status
        self._data = data if data is not None else {}
        self._text = text

    async def json(self):
        return self._data

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _RaisingResponse:
    """Simulates a network error inside the request context."""

    async def __aenter__(self):
        raise OSError("connection reset")

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """aiohttp.ClientSession stand-in: pops queued responses, records requests."""

    queue: list = []
    requests: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None, timeout=None):
        _FakeSession.requests.append({"url": url, "json": json, "headers": headers})
        return _FakeSession.queue.pop(0)


@pytest.fixture()
def fake_http(monkeypatch):
    """Patch ClientSession with the fake and make backoff sleeps instant."""
    _FakeSession.queue = []
    _FakeSession.requests = []
    monkeypatch.setattr(client.aiohttp, "ClientSession", _FakeSession)

    async def _no_sleep(_secs):
        return None

    monkeypatch.setattr(client.asyncio, "sleep", _no_sleep)
    return _FakeSession


def _ok_data(text="hello", inp=100, out=50):
    return {"choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": inp, "completion_tokens": out}}


def test_call_openai_success_returns_text_and_usage(monkeypatch, fake_http):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_http.queue = [_FakeResponse(200, _ok_data())]
    text, usage = asyncio.run(client.call("cheap", "sys", "usr"))
    assert text == "hello"
    assert usage["model"] == "gpt-4o-mini" and usage["total_tokens"] == 150
    # gpt-4o-mini: 100/1M*0.15 + 50/1M*0.60
    assert usage["cost_usd"] == pytest.approx(0.000045)
    assert fake_http.requests[0]["headers"]["Authorization"] == "Bearer sk-test"


def test_call_yandex_success_uses_apikey_and_wrapped_model(monkeypatch, fake_http):
    monkeypatch.setenv("YANDEX_API_KEY", "ya-test")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder123")
    fake_http.queue = [_FakeResponse(200, _ok_data("привет"))]
    text, usage = asyncio.run(client.call("cheap", "s", "u", provider="yandex"))
    assert text == "привет"
    assert usage["provider"] == "yandex"
    assert usage["model"] == "gpt://folder123/yandexgpt-lite/latest"
    assert fake_http.requests[0]["headers"]["Authorization"] == "Api-Key ya-test"


def test_call_non200_no_retry(monkeypatch, fake_http):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_http.queue = [_FakeResponse(401, text="unauthorized")]
    text, usage = asyncio.run(client.call("cheap", "s", "u"))
    assert text is None
    assert usage["total_tokens"] == 0
    assert len(fake_http.requests) == 1          # 4xx (кроме 429) не ретраится


def test_call_retries_on_429_then_succeeds(monkeypatch, fake_http):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_http.queue = [_FakeResponse(429), _FakeResponse(200, _ok_data("ok"))]
    text, _ = asyncio.run(client.call("cheap", "s", "u"))
    assert text == "ok"
    assert len(fake_http.requests) == 2


def test_call_5xx_exhausts_retries(monkeypatch, fake_http):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    fake_http.queue = [_FakeResponse(500), _FakeResponse(503)]
    text, usage = asyncio.run(client.call("cheap", "s", "u"))
    assert text is None
    assert len(fake_http.requests) == 2          # retries=1 → 2 попытки
    assert usage["model"] == "gpt-4o-mini"       # usage возвращается и на провале


def test_call_network_exception_retried_then_fails(monkeypatch, fake_http):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    fake_http.queue = [_RaisingResponse(), _RaisingResponse()]
    text, usage = asyncio.run(client.call("cheap", "s", "u"))
    assert text is None and usage["total_tokens"] == 0


def test_call_missing_api_key_short_circuits(fake_http):
    text, usage = asyncio.run(client.call("cheap", "s", "u"))
    assert text is None
    assert usage["provider"] == "openai" and usage["model"] == "gpt-4o-mini"
    assert fake_http.requests == []              # до сети не дошли


def test_call_empty_content_returns_none(monkeypatch, fake_http):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_http.queue = [_FakeResponse(200, _ok_data(""))]
    text, usage = asyncio.run(client.call("cheap", "s", "u"))
    assert text is None
    assert usage["total_tokens"] == 150          # токены посчитаны несмотря на пустой текст
