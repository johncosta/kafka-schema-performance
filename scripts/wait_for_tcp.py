"""Wait until a TCP host:port accepts connections (for docker compose health).

Optional ``--kafka-ready``: after the port accepts TCP, poll until
``kafka-python`` can complete a broker metadata handshake (avoids flaky tests
when the socket is open before Kafka request processing is enabled).
"""

from __future__ import annotations

import argparse
import socket
import sys
import time

# Match ``docker/docker-compose.kafka.yml`` (Kafka 3.8.x); avoids ``check_version``
# races on fast CI and Python 3.14+.
_KAFKA_PYTHON_API_VERSION = (2, 8, 1)


def _wait_kafka_bootstrap(bootstrap: str, deadline: float, interval: float) -> bool:
    from kafka.admin import KafkaAdminClient

    while time.monotonic() < deadline:
        admin: KafkaAdminClient | None = None
        try:
            admin = KafkaAdminClient(
                bootstrap_servers=bootstrap,
                client_id="ksp-wait-tcp",
                api_version=_KAFKA_PYTHON_API_VERSION,
                request_timeout_ms=5000,
            )
            return True
        except Exception:
            time.sleep(interval)
        finally:
            if admin is not None:
                admin.close()
    return False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=19092)
    p.add_argument("--timeout", type=float, default=90.0)
    p.add_argument("--interval", type=float, default=0.5)
    p.add_argument(
        "--kafka-ready",
        action="store_true",
        help=(
            "After TCP is up, wait until kafka-python can connect "
            "(requires kafka-python-ng)."
        ),
    )
    args = p.parse_args()
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((args.host, args.port), timeout=2.0):
                break
        except OSError:
            time.sleep(args.interval)
    else:
        print(f"timeout: {args.host}:{args.port}", file=sys.stderr)
        return 1

    if args.kafka_ready:
        bootstrap = f"{args.host}:{args.port}"
        if not _wait_kafka_bootstrap(bootstrap, deadline, args.interval):
            print(f"timeout: kafka not ready at {bootstrap}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
