"""Verify the exact Router wheel/sdist and an isolated installed import."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


EXPECTED_WHEEL = "agentic_llm_router-0.2.0-py3-none-any.whl"
EXPECTED_SDIST = "agentic_llm_router-0.2.0.tar.gz"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    dist = parser.parse_args().dist.resolve()
    wheel = dist / EXPECTED_WHEEL
    sdist = dist / EXPECTED_SDIST
    if not wheel.is_file() or not sdist.is_file():
        raise SystemExit("exact Router wheel/sdist set is missing")
    artifacts = sorted(path.name for path in dist.iterdir() if path.is_file())
    if artifacts != sorted([EXPECTED_SDIST, EXPECTED_WHEEL]):
        raise SystemExit(f"unexpected dist artifact set: {artifacts}")
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    if "llm_router/__init__.py" not in names or "llm_router/receipt.py" not in names:
        raise SystemExit("Router wheel is missing its public package surface")
    if any(name.endswith("entry_points.txt") for name in names):
        raise SystemExit("Router base package unexpectedly declares an entry point")
    if any(name.startswith("llm_router-0.2.0.dist-info/") for name in names):
        raise SystemExit("wheel uses the unsafe generic distribution coordinate")
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "site"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-deps",
                "--no-compile",
                "--target",
                str(target),
                str(wheel),
            ],
            check=True,
        )
        import_script = """
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
import llm_router as package
assert package.__version__ == "0.2.0"
assert package.INVOCATION_RECEIPT_V1 == "llm-router-invocation-receipt-v1.0"
"""
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                import_script,
                str(target),
            ],
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
