"""Wait until a TCP host:port accepts connections (for docker compose health)."""

from __future__ import annotations

import argparse
import socket
import sys
import time


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=19092)
    p.add_argument("--timeout", type=float, default=90.0)
    p.add_argument("--interval", type=float, default=0.5)
    args = p.parse_args()
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((args.host, args.port), timeout=2.0):
                return 0
        except OSError:
            time.sleep(args.interval)
    print(f"timeout: {args.host}:{args.port}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
