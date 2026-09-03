from __future__ import annotations

import subprocess
import sys
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


def test_public_package_import_has_no_process_or_network_side_effect() -> None:
    script = """
import sys

forbidden = {
    "os.posix_spawn",
    "os.spawn",
    "os.system",
    "socket.__new__",
    "socket.bind",
    "socket.connect",
    "socket.getaddrinfo",
    "subprocess.Popen",
}

def audit(event, args):
    if event in forbidden:
        raise RuntimeError(f"forbidden import side effect: {event}")

sys.addaudithook(audit)
sys.path.insert(0, sys.argv[1])
from llm_router import call
assert callable(call)
"""
    subprocess.run(
        [sys.executable, "-I", "-c", script, str(ROOT / "src")],
        check=True,
        capture_output=True,
        text=True,
    )
