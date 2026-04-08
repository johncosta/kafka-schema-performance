from __future__ import annotations

import importlib.metadata
import platform
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
