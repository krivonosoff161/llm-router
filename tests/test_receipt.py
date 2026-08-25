from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from llm_router import (
    InvocationAttemptV1,
    InvocationReceiptError,
    build_invocation_receipt_v1,
    decode_invocation_receipt_v1,
    encode_invocation_receipt_v1,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _attempt(
    outcome: str = "success",
    *,
    index: int = 1,
    status: int | None = 200,
    response: str | None = None,
) -> InvocationAttemptV1:
    reason = {
        "rate_limited": "provider.rate_limited",
        "server_error": "provider.server_error",
        "nonretryable_http_error": "provider.nonretryable_http_error",
        "network_error": "provider.network_error",
        "invalid_response": "provider.invalid_response",
        "success": "provider.success",
    }[outcome]
    return InvocationAttemptV1(
        attempt_index=index,
        outcome=outcome,
        http_status=status,
        reason_code=reason,
        response_payload_sha256=_sha(response) if response else None,
    )


def _success(**overrides):
    values = {
        "occurred_at": "2026-08-24T12:00:00.000000Z",
        "producer_id_hash": _sha("producer"),
        "request_payload_sha256": _sha("request"),
        "provider_id": "openai-compatible",
        "model_id_sha256": _sha("model"),
        "role": "cheap",
        "attempts": (_attempt(response="response"),),
        "terminal_status": "success",
        "response_payload_sha256": _sha("response"),
        "output_text_sha256": _sha("output"),
        "usage_provenance": "provider_reported",
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "pricing_source": "illustrative_builtin",
        "pricing_source_ref_sha256": _sha("illustrative-price-table-v1"),
        "input_rate_usd_nanos_per_million": 150_000_000,
        "output_rate_usd_nanos_per_million": 600_000_000,
    }
    values.update(overrides)
    return build_invocation_receipt_v1(**values)


def _canonical(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )


def test_round_trip_is_canonical_and_content_bound() -> None:
    receipt = _success()
    payload = encode_invocation_receipt_v1(receipt)

    assert decode_invocation_receipt_v1(payload) == receipt
    assert payload.endswith(b"\n")
    assert receipt.cost_usd_nanos == 45_000
    assert receipt.cost_local_nanos == 45_000
    assert receipt.invoice_authoritative is False
    assert receipt.operational_authority == "none"


def test_receipt_id_changes_with_content() -> None:
    assert _success(role="cheap").receipt_id != _success(role="audit").receipt_id


@pytest.mark.parametrize(
    ("outcome", "status"),
    [
        ("rate_limited", 500),
        ("server_error", 429),
        ("nonretryable_http_error", 429),
        ("network_error", 200),
    ],
)
def test_attempt_status_semantics_fail_closed(outcome: str, status: int | None) -> None:
    with pytest.raises(InvocationReceiptError):
        _attempt(outcome, status=status)


def test_attempt_reason_is_not_free_text() -> None:
    with pytest.raises(InvocationReceiptError):
        InvocationAttemptV1(1, "network_error", None, "secret endpoint failed", None)


def test_retry_chain_must_be_contiguous_and_retryable() -> None:
    retry = _attempt("server_error", index=1, status=503)
    success = _attempt(index=2, response="response")
    assert _success(attempts=(retry, success)).attempts == (retry, success)

    with pytest.raises(InvocationReceiptError):
        _success(attempts=(replace(retry, attempt_index=2), success))
    with pytest.raises(InvocationReceiptError):
        _success(attempts=(_attempt("nonretryable_http_error", status=401), success))


def test_retry_exhaustion_has_no_usage_or_output() -> None:
    receipt = build_invocation_receipt_v1(
        occurred_at="2026-08-24T12:00:00.000000Z",
        producer_id_hash=_sha("producer"),
        request_payload_sha256=_sha("request"),
        provider_id="openai-compatible",
        model_id_sha256=_sha("model"),
        role="cheap",
        attempts=(_attempt("network_error", status=None),),
        terminal_status="retry_exhausted",
        response_payload_sha256=None,
        output_text_sha256=None,
        usage_provenance="absent",
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        pricing_source="unpriced",
        pricing_source_ref_sha256=None,
        input_rate_usd_nanos_per_million=0,
        output_rate_usd_nanos_per_million=0,
        fx_source="unavailable",
        currency="XXX",
        fx_rate_local_nanos_per_usd=0,
        fx_source_ref_sha256=None,
    )
    assert receipt.cost_usd_nanos == 0


def test_missing_configuration_has_no_attempts() -> None:
    receipt = build_invocation_receipt_v1(
        occurred_at="2026-08-24T12:00:00.000000Z",
        producer_id_hash=_sha("producer"),
        request_payload_sha256=_sha("request"),
        provider_id="openai-compatible",
        model_id_sha256=_sha("model"),
        role="cheap",
        attempts=(),
        terminal_status="missing_configuration",
        response_payload_sha256=None,
        output_text_sha256=None,
        usage_provenance="absent",
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        pricing_source="unpriced",
        pricing_source_ref_sha256=None,
        input_rate_usd_nanos_per_million=0,
        output_rate_usd_nanos_per_million=0,
    )
    assert receipt.terminal_reason_code == "router.missing_configuration"


def test_empty_content_keeps_response_and_usage_but_no_output_digest() -> None:
    receipt = _success(terminal_status="empty_content", output_text_sha256=None)
    assert receipt.output_text_sha256 is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"input_tokens": -1},
        {"input_tokens": True},
        {"input_tokens": "100"},
        {"total_tokens": 151},
        {"role": "root"},
        {"provider_id": "https://private.example"},
        {"occurred_at": "2026-08-24T12:00:00Z"},
    ],
)
def test_strict_types_ranges_and_tokens(overrides: dict[str, object]) -> None:
    with pytest.raises(InvocationReceiptError):
        _success(**overrides)


def test_operator_declared_fx_uses_half_even_fixed_point() -> None:
    receipt = _success(
        currency="RUB",
        fx_source="operator_declared",
        fx_rate_local_nanos_per_usd=90 * 1_000_000_000,
        fx_source_ref_sha256=_sha("operator-fx-snapshot"),
    )
    assert receipt.cost_local_nanos == 4_050_000


def test_unpriced_usage_cannot_hide_nonzero_rates() -> None:
    with pytest.raises(InvocationReceiptError):
        _success(pricing_source="unpriced")


def test_priced_and_operator_fx_require_exact_source_artifact_digests() -> None:
    with pytest.raises(InvocationReceiptError, match="source artifact"):
        _success(pricing_source_ref_sha256=None)
    with pytest.raises(InvocationReceiptError, match="operator-declared FX"):
        _success(
            currency="RUB",
            fx_source="operator_declared",
            fx_rate_local_nanos_per_usd=90 * 1_000_000_000,
            fx_source_ref_sha256=None,
        )


def test_direct_construction_cannot_retain_mutable_attempt_list() -> None:
    value = _success().as_dict()
    value["attempts"] = [_attempt(response="response")]
    with pytest.raises(InvocationReceiptError, match="immutable attempt tuple"):
        # Bypass the JSON decoder to exercise the exported dataclass surface.
        from llm_router import InvocationReceiptV1

        InvocationReceiptV1(**value)


def test_tampered_receipt_and_pricing_bindings_fail() -> None:
    value = _success().as_dict()
    value["receipt_id"] = _sha("forged")
    with pytest.raises(InvocationReceiptError, match="receipt_id"):
        decode_invocation_receipt_v1(_canonical(value))

    value = _success().as_dict()
    value["pricing_ref_sha256"] = _sha("forged")
    value["receipt_id"] = _sha("also-forged")
    with pytest.raises(InvocationReceiptError, match="pricing reference"):
        decode_invocation_receipt_v1(_canonical(value))


def test_unknown_and_duplicate_fields_fail() -> None:
    value = _success().as_dict()
    value["api_key"] = "must-not-exist"
    with pytest.raises(InvocationReceiptError, match="fields"):
        decode_invocation_receipt_v1(_canonical(value))

    payload = encode_invocation_receipt_v1(_success())
    duplicate = payload.replace(b'{"attempts":', b'{"attempts":[],"attempts":', 1)
    with pytest.raises(InvocationReceiptError):
        decode_invocation_receipt_v1(duplicate)


def test_noncanonical_json_and_nonfinite_numbers_fail() -> None:
    payload = encode_invocation_receipt_v1(_success())
    with pytest.raises(InvocationReceiptError, match="canonical"):
        decode_invocation_receipt_v1(b" " + payload)
    with pytest.raises(InvocationReceiptError):
        decode_invocation_receipt_v1(payload.replace(b'"input_tokens":100', b'"input_tokens":NaN'))


def test_contract_contains_no_raw_or_credential_fields() -> None:
    fields = set(_success().as_dict())
    forbidden = {
        "api_key",
        "authorization",
        "base_url",
        "endpoint",
        "exception",
        "prompt",
        "response_body",
        "system",
        "text",
        "user",
    }
    assert fields.isdisjoint(forbidden)
