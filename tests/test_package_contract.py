from __future__ import annotations

from pathlib import Path

import llm_router


ROOT = Path(__file__).resolve().parents[1]


def test_distribution_coordinate_is_unique_and_versioned() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "agentic-llm-router"' in pyproject
    assert 'version = "0.2.0"' in pyproject
    assert '\nname = "llm-router"' not in pyproject
    assert llm_router.__version__ == "0.2.0"


def test_package_declares_no_automatic_harness_entry_point() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.entry-points" not in pyproject
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "generic PyPI name `llm-router` belongs to another project" in readme
