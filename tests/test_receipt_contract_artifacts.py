from __future__ import annotations

import json
from pathlib import Path

from llm_router import invocation_receipt_v1_json_schema


ROOT = Path(__file__).resolve().parents[1]


def test_generated_receipt_schema_is_current_and_closed() -> None:
    path = ROOT / "contracts" / "router-invocation-receipt.v1.schema.json"
    observed = json.loads(path.read_text(encoding="utf-8"))

    assert observed == invocation_receipt_v1_json_schema()
    assert observed["additionalProperties"] is False
    assert set(observed["required"]) == set(observed["properties"])
    attempt = observed["properties"]["attempts"]["items"]
    assert attempt["additionalProperties"] is False
    assert set(attempt["required"]) == set(attempt["properties"])


def test_public_contract_artifacts_do_not_expand_runtime_authority() -> None:
    docs = (ROOT / "docs" / "invocation-receipt.md").read_text(encoding="utf-8")
    schema = (ROOT / "contracts" / "router-invocation-receipt.v1.schema.json").read_text(
        encoding="utf-8"
    )

    assert "operational_authority=none" in docs
    assert '"operational_authority"' in schema
    assert '"const": "none"' in schema
    assert "provider calls require fresh explicit authority" in (
        ROOT / "AGENTS.md"
    ).read_text(encoding="utf-8")
