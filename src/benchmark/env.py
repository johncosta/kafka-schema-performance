from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
import sys
from typing import Any


def _version(dist_name: str) -> str:
    try:
        return importlib.metadata.version(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def collect_environment() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {
            "fastavro": _version("fastavro"),
            "protobuf": _version("protobuf"),
            "orjson": _version("orjson"),
            "typer": _version("typer"),
            "pyyaml": _version("PyYAML"),
            "zstandard": _version("zstandard"),
        },
    }


def collect_pip_freeze_integrity() -> dict[str, Any]:
    """Sorted ``pip freeze`` output and SHA-256 (Phase 8 reproducibility hint)."""

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {
            "method": "pip freeze",
            "error": str(e),
            "lines": [],
            "sha256": "",
            "pip_exit_code": None,
        }

    raw = proc.stdout.strip()
    lines = sorted(raw.splitlines()) if raw else []
    joined = "\n".join(lines).encode("utf-8")
    digest = hashlib.sha256(joined).hexdigest() if lines else ""
    return {
        "method": "pip freeze",
        "lines": lines,
        "sha256": digest,
        "line_count": len(lines),
        "pip_exit_code": proc.returncode,
        "note": (
            "Not a full SBOM; freeze reflects the active interpreter environment. "
            "Compare sha256 across runs on the same machine class for drift checks."
        ),
    }
