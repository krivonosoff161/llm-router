"""Generate or verify the canonical Router invocation receipt JSON Schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from llm_router.receipt import invocation_receipt_v1_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "contracts" / "router-invocation-receipt.v1.schema.json"


def expected_bytes() -> bytes:
    return (
        json.dumps(
            invocation_receipt_v1_json_schema(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("check", "write"))
    args = parser.parse_args()
    expected = expected_bytes()
    if args.mode == "write":
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_PATH.write_bytes(expected)
        return 0
    if not SCHEMA_PATH.is_file() or SCHEMA_PATH.read_bytes() != expected:
        print("router invocation receipt schema drift", file=sys.stderr)
        return 1
    print("router invocation receipt schema: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
