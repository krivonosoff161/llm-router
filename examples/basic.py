# -*- coding: utf-8 -*-
"""Minimal single call. Set a provider + key first (see .env.example)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # run from a clone, no install

from llm_router import call  # noqa: E402


async def main() -> None:
    text, usage = await call("cheap", "You are concise.", "Name 3 primary colors.")
    print("reply:", text)
    print("usage:", usage)


if __name__ == "__main__":
    asyncio.run(main())
