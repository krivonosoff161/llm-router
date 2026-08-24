"""Canonical, authority-free invocation receipt V1.

The receipt is an offline interchange contract.  It records sanitized routing,
attempt, usage, and fixed-point cost evidence without retaining credentials,
endpoints, prompts, model output, provider response bodies, or exception text.
It does not invoke a provider and it is not invoice or provider attestation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Iterable, Mapping


INVOCATION_RECEIPT_V1: Final = "llm-router-invocation-receipt-v1.0"
MAX_RECEIPT_BYTES: Final = 1_048_576
MAX_ATTEMPTS: Final = 16
NANOS_PER_UNIT: Final = 1_000_000_000
TOKENS_PER_MILLION: Final = 1_000_000
MAX_COUNT: Final = 1_000_000_000_000
MAX_FIXED_POINT: Final = 10**24
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
TOKEN_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
CURRENCY_PATTERN: Final = re.compile(r"^[A-Z]{3}$")
USD_IDENTITY_SOURCE_SHA256: Final = hashlib.sha256(
    b"llm-router/fx-identity/v1\0USD=USD"
).hexdigest()

ROLES: Final = frozenset({"cheap", "mid", "chief", "audit"})
ATTEMPT_OUTCOMES: Final = frozenset(
    {
        "rate_limited",
        "server_error",
        "nonretryable_http_error",
        "network_error",
        "invalid_response",
        "success",
    }
)
TERMINAL_STATUSES: Final = frozenset(
    {
        "success",
        "empty_content",
        "missing_configuration",
        "nonretryable_http_error",
        "retry_exhausted",
    }
)
USAGE_PROVENANCE: Final = frozenset({"provider_reported", "absent"})
PRICING_SOURCES: Final = frozenset({"illustrative_builtin", "operator_override", "unpriced"})
FX_SOURCES: Final = frozenset({"identity", "operator_declared", "unavailable"})

ATTEMPT_REASON: Final = {
    "rate_limited": "provider.rate_limited",
    "server_error": "provider.server_error",
    "nonretryable_http_error": "provider.nonretryable_http_error",
    "network_error": "provider.network_error",
    "invalid_response": "provider.invalid_response",
    "success": "provider.success",
}
TERMINAL_REASON: Final = {
    "success": "router.success",
    "empty_content": "router.empty_content",
    "missing_configuration": "router.missing_configuration",
    "nonretryable_http_error": "router.nonretryable_http_error",
    "retry_exhausted": "router.retry_exhausted",
}
RETRYABLE_OUTCOMES: Final = frozenset(
    {"rate_limited", "server_error", "network_error", "invalid_response"}
)


class InvocationReceiptError(ValueError):
    """Raised when invocation receipt data violates the closed V1 contract."""


@dataclass(frozen=True)
class InvocationAttemptV1:
    """One sanitized invocation attempt; response bytes are represented by digest only."""

    attempt_index: int
    outcome: str
    http_status: int | None
    reason_code: str
    response_payload_sha256: str | None

    def __post_init__(self) -> None:
        _require_int("attempt_index", self.attempt_index, minimum=1, maximum=MAX_ATTEMPTS)
        if self.outcome not in ATTEMPT_OUTCOMES:
            raise InvocationReceiptError("attempt outcome is not supported")
        if self.reason_code != ATTEMPT_REASON[self.outcome]:
            raise InvocationReceiptError("attempt reason code does not match outcome")
        _validate_http_status(self.outcome, self.http_status)
        _require_optional_sha256("response_payload_sha256", self.response_payload_sha256)

    def as_dict(self) -> dict[str, object]:
        return {
            "attempt_index": self.attempt_index,
            "http_status": self.http_status,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "response_payload_sha256": self.response_payload_sha256,
        }


@dataclass(frozen=True)
class InvocationReceiptV1:
    """Canonical content-bound invocation evidence with no operational authority."""

    schema_version: str
    receipt_id: str
    occurred_at: str
    producer_id_hash: str
    request_payload_sha256: str
    provider_id: str
    model_id_sha256: str
    role: str
    attempts: tuple[InvocationAttemptV1, ...]
    terminal_status: str
    terminal_reason_code: str
    response_payload_sha256: str | None
    output_text_sha256: str | None
    usage_provenance: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    pricing_source: str
    pricing_source_ref_sha256: str | None
    input_rate_usd_nanos_per_million: int
    output_rate_usd_nanos_per_million: int
    rounding_mode: str
    pricing_ref_sha256: str
    cost_usd_nanos: int
    currency: str
    fx_source: str
    fx_source_ref_sha256: str | None
    fx_rate_local_nanos_per_usd: int
    cost_local_nanos: int
    invoice_authoritative: bool
    operational_authority: str

    def __post_init__(self) -> None:
        if self.schema_version != INVOCATION_RECEIPT_V1:
            raise InvocationReceiptError("unsupported invocation receipt schema")
        _require_sha256("receipt_id", self.receipt_id)
        _validate_utc_timestamp(self.occurred_at)
        _require_sha256("producer_id_hash", self.producer_id_hash)
        _require_sha256("request_payload_sha256", self.request_payload_sha256)
        if not TOKEN_PATTERN.fullmatch(self.provider_id):
            raise InvocationReceiptError("provider_id must be a bounded canonical token")
        _require_sha256("model_id_sha256", self.model_id_sha256)
        if self.role not in ROLES:
            raise InvocationReceiptError("role is not supported")
        if not isinstance(self.attempts, tuple) or any(
            not isinstance(item, InvocationAttemptV1) for item in self.attempts
        ):
            raise InvocationReceiptError("attempts must be an immutable attempt tuple")
        if len(self.attempts) > MAX_ATTEMPTS:
            raise InvocationReceiptError("attempt count exceeds the V1 limit")
        if tuple(item.attempt_index for item in self.attempts) != tuple(
            range(1, len(self.attempts) + 1)
        ):
            raise InvocationReceiptError("attempt indices must be contiguous and one-based")
        if self.terminal_status not in TERMINAL_STATUSES:
            raise InvocationReceiptError("terminal status is not supported")
        if self.terminal_reason_code != TERMINAL_REASON[self.terminal_status]:
            raise InvocationReceiptError("terminal reason code does not match status")
        _require_optional_sha256("response_payload_sha256", self.response_payload_sha256)
        _require_optional_sha256("output_text_sha256", self.output_text_sha256)
        if self.usage_provenance not in USAGE_PROVENANCE:
            raise InvocationReceiptError("usage provenance is not supported")
        for field, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
            ("total_tokens", self.total_tokens),
        ):
            _require_int(field, value, minimum=0, maximum=MAX_COUNT)
        if self.pricing_source not in PRICING_SOURCES:
            raise InvocationReceiptError("pricing source is not supported")
        _require_optional_sha256("pricing_source_ref_sha256", self.pricing_source_ref_sha256)
        for field, value in (
            ("input_rate_usd_nanos_per_million", self.input_rate_usd_nanos_per_million),
            ("output_rate_usd_nanos_per_million", self.output_rate_usd_nanos_per_million),
            ("cost_usd_nanos", self.cost_usd_nanos),
            ("fx_rate_local_nanos_per_usd", self.fx_rate_local_nanos_per_usd),
            ("cost_local_nanos", self.cost_local_nanos),
        ):
            _require_int(field, value, minimum=0, maximum=MAX_FIXED_POINT)
        if self.rounding_mode != "half_even":
            raise InvocationReceiptError("V1 fixed-point rounding must be half_even")
        _require_sha256("pricing_ref_sha256", self.pricing_ref_sha256)
        if not CURRENCY_PATTERN.fullmatch(self.currency):
            raise InvocationReceiptError("currency must be a three-letter uppercase code")
        if self.fx_source not in FX_SOURCES:
            raise InvocationReceiptError("FX source is not supported")
        _require_optional_sha256("fx_source_ref_sha256", self.fx_source_ref_sha256)
        if self.invoice_authoritative is not False:
            raise InvocationReceiptError("invocation receipts cannot claim invoice authority")
        if self.operational_authority != "none":
            raise InvocationReceiptError("invocation receipts carry no operational authority")
        self._validate_attempt_state()
        self._validate_usage_and_cost()
        if self.pricing_ref_sha256 != _pricing_reference(self):
            raise InvocationReceiptError("pricing reference does not bind fixed-point inputs")
        if self.receipt_id != _receipt_identity(self.as_dict(include_receipt_id=False)):
            raise InvocationReceiptError("receipt_id does not bind canonical receipt content")

    def _validate_attempt_state(self) -> None:
        if self.terminal_status == "missing_configuration":
            if self.attempts:
                raise InvocationReceiptError("missing configuration cannot record attempts")
        else:
            if not self.attempts:
                raise InvocationReceiptError("terminal invocation requires at least one attempt")
            if any(item.outcome not in RETRYABLE_OUTCOMES for item in self.attempts[:-1]):
                raise InvocationReceiptError("only retryable outcomes may precede the final attempt")
            final = self.attempts[-1]
            expected_final = {
                "success": "success",
                "empty_content": "success",
                "nonretryable_http_error": "nonretryable_http_error",
            }.get(self.terminal_status)
            if expected_final is not None and final.outcome != expected_final:
                raise InvocationReceiptError("final attempt outcome does not match terminal status")
            if self.terminal_status == "retry_exhausted" and final.outcome not in RETRYABLE_OUTCOMES:
                raise InvocationReceiptError("retry exhaustion must end in a retryable outcome")

        final_response = self.attempts[-1].response_payload_sha256 if self.attempts else None
        if self.response_payload_sha256 != final_response:
            raise InvocationReceiptError("receipt response digest must match the final attempt")
        if self.terminal_status in {"success", "empty_content"} and final_response is None:
            raise InvocationReceiptError("successful HTTP response requires a response digest")
        if self.terminal_status == "success" and self.output_text_sha256 is None:
            raise InvocationReceiptError("successful non-empty output requires an output digest")
        if self.terminal_status != "success" and self.output_text_sha256 is not None:
            raise InvocationReceiptError("only successful non-empty output may carry an output digest")

    def _validate_usage_and_cost(self) -> None:
        if self.usage_provenance == "absent":
            if any((self.input_tokens, self.output_tokens, self.total_tokens)):
                raise InvocationReceiptError("absent usage must use zero token counts")
        elif self.total_tokens != self.input_tokens + self.output_tokens:
            raise InvocationReceiptError("total_tokens must equal input_tokens plus output_tokens")

        if self.terminal_status not in {"success", "empty_content"}:
            if self.usage_provenance != "absent":
                raise InvocationReceiptError("failed invocation cannot claim provider usage")

        rates = (
            self.input_rate_usd_nanos_per_million,
            self.output_rate_usd_nanos_per_million,
        )
        if self.pricing_source == "unpriced":
            if any(rates) or self.cost_usd_nanos or self.pricing_source_ref_sha256 is not None:
                raise InvocationReceiptError(
                    "unpriced usage must use zero rates, zero cost, and no source reference"
                )
        else:
            if self.pricing_source_ref_sha256 is None:
                raise InvocationReceiptError("priced usage requires a source artifact digest")
            if not any(rates):
                raise InvocationReceiptError("priced usage requires at least one positive rate")
            expected_usd = _round_ratio_half_even(
                self.input_tokens * rates[0] + self.output_tokens * rates[1],
                TOKENS_PER_MILLION,
            )
            if self.cost_usd_nanos != expected_usd:
                raise InvocationReceiptError("USD cost does not match fixed-point token arithmetic")

        if self.fx_source == "identity":
            if (
                self.currency != "USD"
                or self.fx_rate_local_nanos_per_usd != NANOS_PER_UNIT
                or self.cost_local_nanos != self.cost_usd_nanos
                or self.fx_source_ref_sha256 != USD_IDENTITY_SOURCE_SHA256
            ):
                raise InvocationReceiptError("identity FX must preserve USD nanos exactly")
        elif self.fx_source == "unavailable":
            if (
                self.currency != "XXX"
                or self.fx_rate_local_nanos_per_usd != 0
                or self.cost_local_nanos != 0
                or self.fx_source_ref_sha256 is not None
            ):
                raise InvocationReceiptError("unavailable FX must use XXX and zero values")
        else:
            if (
                self.currency in {"USD", "XXX"}
                or self.fx_rate_local_nanos_per_usd <= 0
                or self.fx_source_ref_sha256 is None
            ):
                raise InvocationReceiptError("operator-declared FX requires a non-USD currency and rate")
            expected_local = _round_ratio_half_even(
                self.cost_usd_nanos * self.fx_rate_local_nanos_per_usd,
                NANOS_PER_UNIT,
            )
            if self.cost_local_nanos != expected_local:
                raise InvocationReceiptError("local cost does not match fixed-point FX arithmetic")

    def as_dict(self, *, include_receipt_id: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "attempts": [item.as_dict() for item in self.attempts],
            "cost_local_nanos": self.cost_local_nanos,
            "cost_usd_nanos": self.cost_usd_nanos,
            "currency": self.currency,
            "fx_rate_local_nanos_per_usd": self.fx_rate_local_nanos_per_usd,
            "fx_source": self.fx_source,
            "fx_source_ref_sha256": self.fx_source_ref_sha256,
            "input_rate_usd_nanos_per_million": self.input_rate_usd_nanos_per_million,
            "input_tokens": self.input_tokens,
            "invoice_authoritative": self.invoice_authoritative,
            "model_id_sha256": self.model_id_sha256,
            "occurred_at": self.occurred_at,
            "operational_authority": self.operational_authority,
            "output_rate_usd_nanos_per_million": self.output_rate_usd_nanos_per_million,
            "output_text_sha256": self.output_text_sha256,
            "output_tokens": self.output_tokens,
            "pricing_ref_sha256": self.pricing_ref_sha256,
            "pricing_source": self.pricing_source,
            "pricing_source_ref_sha256": self.pricing_source_ref_sha256,
            "producer_id_hash": self.producer_id_hash,
            "provider_id": self.provider_id,
            "request_payload_sha256": self.request_payload_sha256,
            "response_payload_sha256": self.response_payload_sha256,
            "role": self.role,
            "rounding_mode": self.rounding_mode,
            "schema_version": self.schema_version,
            "terminal_reason_code": self.terminal_reason_code,
            "terminal_status": self.terminal_status,
            "total_tokens": self.total_tokens,
            "usage_provenance": self.usage_provenance,
        }
        if include_receipt_id:
            payload["receipt_id"] = self.receipt_id
        return payload


def build_invocation_receipt_v1(
    *,
    occurred_at: str,
    producer_id_hash: str,
    request_payload_sha256: str,
    provider_id: str,
    model_id_sha256: str,
    role: str,
    attempts: Iterable[InvocationAttemptV1],
    terminal_status: str,
    response_payload_sha256: str | None,
    output_text_sha256: str | None,
    usage_provenance: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    pricing_source: str,
    pricing_source_ref_sha256: str | None,
    input_rate_usd_nanos_per_million: int,
    output_rate_usd_nanos_per_million: int,
    currency: str = "USD",
    fx_source: str = "identity",
    fx_rate_local_nanos_per_usd: int = NANOS_PER_UNIT,
    fx_source_ref_sha256: str | None = USD_IDENTITY_SOURCE_SHA256,
) -> InvocationReceiptV1:
    """Build and validate one receipt from already-observed sanitized values."""

    attempt_tuple = tuple(attempts)
    if any(not isinstance(item, InvocationAttemptV1) for item in attempt_tuple):
        raise InvocationReceiptError("attempts must contain InvocationAttemptV1 values")
    for field, value, maximum in (
        ("input_tokens", input_tokens, MAX_COUNT),
        ("output_tokens", output_tokens, MAX_COUNT),
        ("total_tokens", total_tokens, MAX_COUNT),
        (
            "input_rate_usd_nanos_per_million",
            input_rate_usd_nanos_per_million,
            MAX_FIXED_POINT,
        ),
        (
            "output_rate_usd_nanos_per_million",
            output_rate_usd_nanos_per_million,
            MAX_FIXED_POINT,
        ),
        ("fx_rate_local_nanos_per_usd", fx_rate_local_nanos_per_usd, MAX_FIXED_POINT),
    ):
        _require_int(field, value, minimum=0, maximum=maximum)
    if pricing_source not in PRICING_SOURCES:
        raise InvocationReceiptError("pricing source is not supported")
    if fx_source not in FX_SOURCES:
        raise InvocationReceiptError("FX source is not supported")
    cost_usd_nanos = 0
    if pricing_source != "unpriced":
        cost_usd_nanos = _round_ratio_half_even(
            input_tokens * input_rate_usd_nanos_per_million
            + output_tokens * output_rate_usd_nanos_per_million,
            TOKENS_PER_MILLION,
        )
    if fx_source == "identity":
        cost_local_nanos = cost_usd_nanos
    elif fx_source == "unavailable":
        cost_local_nanos = 0
    else:
        cost_local_nanos = _round_ratio_half_even(
            cost_usd_nanos * fx_rate_local_nanos_per_usd,
            NANOS_PER_UNIT,
        )
    pricing_values = {
        "currency": currency,
        "fx_rate_local_nanos_per_usd": fx_rate_local_nanos_per_usd,
        "fx_source": fx_source,
        "fx_source_ref_sha256": fx_source_ref_sha256,
        "input_rate_usd_nanos_per_million": input_rate_usd_nanos_per_million,
        "output_rate_usd_nanos_per_million": output_rate_usd_nanos_per_million,
        "pricing_source": pricing_source,
        "pricing_source_ref_sha256": pricing_source_ref_sha256,
        "rounding_mode": "half_even",
    }
    payload: dict[str, object] = {
        "attempts": [item.as_dict() for item in attempt_tuple],
        "cost_local_nanos": cost_local_nanos,
        "cost_usd_nanos": cost_usd_nanos,
        "currency": currency,
        "fx_rate_local_nanos_per_usd": fx_rate_local_nanos_per_usd,
        "fx_source": fx_source,
        "fx_source_ref_sha256": fx_source_ref_sha256,
        "input_rate_usd_nanos_per_million": input_rate_usd_nanos_per_million,
        "input_tokens": input_tokens,
        "invoice_authoritative": False,
        "model_id_sha256": model_id_sha256,
        "occurred_at": occurred_at,
        "operational_authority": "none",
        "output_rate_usd_nanos_per_million": output_rate_usd_nanos_per_million,
        "output_text_sha256": output_text_sha256,
        "output_tokens": output_tokens,
        "pricing_ref_sha256": _domain_object_digest(
            "llm-router/pricing-reference/v1", pricing_values
        ),
        "pricing_source": pricing_source,
        "pricing_source_ref_sha256": pricing_source_ref_sha256,
        "producer_id_hash": producer_id_hash,
        "provider_id": provider_id,
        "request_payload_sha256": request_payload_sha256,
        "response_payload_sha256": response_payload_sha256,
        "role": role,
        "rounding_mode": "half_even",
        "schema_version": INVOCATION_RECEIPT_V1,
        "terminal_reason_code": TERMINAL_REASON.get(terminal_status, ""),
        "terminal_status": terminal_status,
        "total_tokens": total_tokens,
        "usage_provenance": usage_provenance,
    }
    payload["receipt_id"] = _receipt_identity(payload)
    return _receipt_from_mapping(payload)


def encode_invocation_receipt_v1(receipt: InvocationReceiptV1) -> bytes:
    """Encode exact canonical UTF-8 JSON with one terminal LF."""

    validated = _receipt_from_mapping(receipt.as_dict())
    return _canonical_bytes(validated.as_dict(), trailing_lf=True)


def decode_invocation_receipt_v1(payload: bytes) -> InvocationReceiptV1:
    """Decode exact canonical V1 bytes; ambiguity and drift fail closed."""

    if not isinstance(payload, bytes):
        raise InvocationReceiptError("receipt payload must be bytes")
    if not payload or len(payload) > MAX_RECEIPT_BYTES:
        raise InvocationReceiptError("receipt payload size is outside the V1 limit")
    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, InvocationReceiptError) as exc:
        raise InvocationReceiptError("receipt payload is not unambiguous UTF-8 JSON") from exc
    if not isinstance(decoded, dict):
        raise InvocationReceiptError("receipt payload must be a JSON object")
    receipt = _receipt_from_mapping(decoded)
    if encode_invocation_receipt_v1(receipt) != payload:
        raise InvocationReceiptError("receipt payload is not canonical V1 JSON")
    return receipt


def invocation_receipt_v1_json_schema() -> dict[str, object]:
    """Return the closed shape schema; Python validation owns semantic invariants."""

    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    optional_sha = {"oneOf": [sha, {"type": "null"}]}
    integer = {"type": "integer", "minimum": 0, "maximum": MAX_FIXED_POINT}
    attempt = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "attempt_index",
            "http_status",
            "outcome",
            "reason_code",
            "response_payload_sha256",
        ],
        "properties": {
            "attempt_index": {"type": "integer", "minimum": 1, "maximum": MAX_ATTEMPTS},
            "http_status": {
                "oneOf": [
                    {"type": "integer", "minimum": 100, "maximum": 599},
                    {"type": "null"},
                ]
            },
            "outcome": {"type": "string", "enum": sorted(ATTEMPT_OUTCOMES)},
            "reason_code": {"type": "string", "enum": sorted(ATTEMPT_REASON.values())},
            "response_payload_sha256": optional_sha,
        },
    }
    properties: dict[str, object] = {
        "attempts": {"type": "array", "maxItems": MAX_ATTEMPTS, "items": attempt},
        "cost_local_nanos": integer,
        "cost_usd_nanos": integer,
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
        "fx_rate_local_nanos_per_usd": integer,
        "fx_source": {"type": "string", "enum": sorted(FX_SOURCES)},
        "fx_source_ref_sha256": optional_sha,
        "input_rate_usd_nanos_per_million": integer,
        "input_tokens": {"type": "integer", "minimum": 0, "maximum": MAX_COUNT},
        "invoice_authoritative": {"const": False},
        "model_id_sha256": sha,
        "occurred_at": {"type": "string", "format": "date-time", "maxLength": 32},
        "operational_authority": {"const": "none"},
        "output_rate_usd_nanos_per_million": integer,
        "output_text_sha256": optional_sha,
        "output_tokens": {"type": "integer", "minimum": 0, "maximum": MAX_COUNT},
        "pricing_ref_sha256": sha,
        "pricing_source": {"type": "string", "enum": sorted(PRICING_SOURCES)},
        "pricing_source_ref_sha256": optional_sha,
        "producer_id_hash": sha,
        "provider_id": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]{0,63}$"},
        "receipt_id": sha,
        "request_payload_sha256": sha,
        "response_payload_sha256": optional_sha,
        "role": {"type": "string", "enum": sorted(ROLES)},
        "rounding_mode": {"const": "half_even"},
        "schema_version": {"const": INVOCATION_RECEIPT_V1},
        "terminal_reason_code": {"type": "string", "enum": sorted(TERMINAL_REASON.values())},
        "terminal_status": {"type": "string", "enum": sorted(TERMINAL_STATUSES)},
        "total_tokens": {"type": "integer", "minimum": 0, "maximum": MAX_COUNT},
        "usage_provenance": {"type": "string", "enum": sorted(USAGE_PROVENANCE)},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/krivonosoff161/llm-router/contracts/router-invocation-receipt.v1.schema.json",
        "title": "LLM Router Invocation Receipt V1",
        "description": (
            "Closed shape schema. Semantic state-machine, binding, and fixed-point "
            "arithmetic checks are authoritative in llm_router.receipt."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": sorted(properties),
        "properties": properties,
    }


def _receipt_from_mapping(value: Mapping[str, Any]) -> InvocationReceiptV1:
    expected = {
        "attempts",
        "cost_local_nanos",
        "cost_usd_nanos",
        "currency",
        "fx_rate_local_nanos_per_usd",
        "fx_source",
        "fx_source_ref_sha256",
        "input_rate_usd_nanos_per_million",
        "input_tokens",
        "invoice_authoritative",
        "model_id_sha256",
        "occurred_at",
        "operational_authority",
        "output_rate_usd_nanos_per_million",
        "output_text_sha256",
        "output_tokens",
        "pricing_ref_sha256",
        "pricing_source",
        "pricing_source_ref_sha256",
        "producer_id_hash",
        "provider_id",
        "receipt_id",
        "request_payload_sha256",
        "response_payload_sha256",
        "role",
        "rounding_mode",
        "schema_version",
        "terminal_reason_code",
        "terminal_status",
        "total_tokens",
        "usage_provenance",
    }
    if set(value) != expected:
        raise InvocationReceiptError("receipt fields do not match V1")
    attempts_value = value["attempts"]
    if not isinstance(attempts_value, list):
        raise InvocationReceiptError("attempts must be a JSON array")
    attempts: list[InvocationAttemptV1] = []
    attempt_fields = {
        "attempt_index",
        "http_status",
        "outcome",
        "reason_code",
        "response_payload_sha256",
    }
    for raw in attempts_value:
        if not isinstance(raw, dict) or set(raw) != attempt_fields:
            raise InvocationReceiptError("attempt fields do not match V1")
        attempts.append(InvocationAttemptV1(**raw))
    values = dict(value)
    values["attempts"] = tuple(attempts)
    try:
        return InvocationReceiptV1(**values)
    except TypeError as exc:
        raise InvocationReceiptError("receipt values do not match V1 types") from exc


def _pricing_reference(receipt: InvocationReceiptV1) -> str:
    return _domain_object_digest(
        "llm-router/pricing-reference/v1",
        {
            "currency": receipt.currency,
            "fx_rate_local_nanos_per_usd": receipt.fx_rate_local_nanos_per_usd,
            "fx_source": receipt.fx_source,
            "fx_source_ref_sha256": receipt.fx_source_ref_sha256,
            "input_rate_usd_nanos_per_million": receipt.input_rate_usd_nanos_per_million,
            "output_rate_usd_nanos_per_million": receipt.output_rate_usd_nanos_per_million,
            "pricing_source": receipt.pricing_source,
            "pricing_source_ref_sha256": receipt.pricing_source_ref_sha256,
            "rounding_mode": receipt.rounding_mode,
        },
    )


def _receipt_identity(payload: Mapping[str, object]) -> str:
    body = dict(payload)
    body.pop("receipt_id", None)
    return hashlib.sha256(
        b"llm-router/invocation-receipt/v1\0" + _canonical_bytes(body, trailing_lf=False)
    ).hexdigest()


def _domain_object_digest(domain: str, value: object) -> str:
    return hashlib.sha256(
        domain.encode("ascii") + b"\0" + _canonical_bytes(value, trailing_lf=False)
    ).hexdigest()


def _canonical_bytes(value: object, *, trailing_lf: bool) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InvocationReceiptError("receipt contains non-canonical JSON data") from exc
    return encoded + (b"\n" if trailing_lf else b"")


def _round_ratio_half_even(numerator: int, denominator: int) -> int:
    _require_int("fixed-point numerator", numerator, minimum=0, maximum=10**42)
    _require_int("fixed-point denominator", denominator, minimum=1, maximum=10**18)
    quotient, remainder = divmod(numerator, denominator)
    twice = remainder * 2
    if twice > denominator or (twice == denominator and quotient % 2):
        quotient += 1
    if quotient > MAX_FIXED_POINT:
        raise InvocationReceiptError("fixed-point result exceeds the V1 limit")
    return quotient


def _validate_http_status(outcome: str, status: int | None) -> None:
    if status is not None:
        _require_int("http_status", status, minimum=100, maximum=599)
    valid = {
        "rate_limited": status == 429,
        "server_error": status is not None and 500 <= status <= 599,
        "nonretryable_http_error": (
            status is not None and 100 <= status <= 499 and status not in {200, 429}
        ),
        "network_error": status is None,
        "invalid_response": status in {None, 200},
        "success": status == 200,
    }
    if not valid[outcome]:
        raise InvocationReceiptError("HTTP status does not match attempt outcome")


def _validate_utc_timestamp(value: object) -> None:
    if not isinstance(value, str) or len(value) > 32:
        raise InvocationReceiptError("occurred_at must be a bounded canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvocationReceiptError("occurred_at is not a timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvocationReceiptError("occurred_at must be timezone-aware")
    normalized = parsed.astimezone(timezone.utc)
    canonical = normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if canonical != value or normalized.year < 1970 or normalized.year > 2100:
        raise InvocationReceiptError("occurred_at is not canonical supported UTC")


def _require_int(name: str, value: object, *, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise InvocationReceiptError(f"{name} must be a bounded integer")


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise InvocationReceiptError(f"{name} must be lowercase SHA-256")


def _require_optional_sha256(name: str, value: object) -> None:
    if value is not None:
        _require_sha256(name, value)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvocationReceiptError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise InvocationReceiptError(f"non-finite JSON constant is forbidden: {value}")
