# -*- coding: utf-8 -*-
"""Show the cheap vs chief tiers and the per-call cost each returns."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # run from a clone, no install

from llm_router import call, model_for  # noqa: E402


async def main() -> None:
    for role in ("cheap", "chief"):
        print(f"[{role}] model = {model_for(role)}")
        text, usage = await call(
            role,
            "You are a market analyst. Answer in one sentence.",
            "Is a widely-known, already-priced catalyst an edge?",
        )
        print(f"  reply: {text}")
        print(f"  cost : {usage['cost_usd']} USD / {usage['cost_local']} {usage['currency']}"
              f"  ({usage['total_tokens']} tokens)\n")


if __name__ == "__main__":
    asyncio.run(main())
