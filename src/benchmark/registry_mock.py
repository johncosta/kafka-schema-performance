"""Local mock Confluent-style schema registry for tier S2 (Phase 6, optional)."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def confluent_schema_response_body() -> bytes:
    """Minimal Schema Registry ``GET /schemas/ids/{id}`` JSON body."""

    schema = json.dumps(
        {
            "type": "record",
            "name": "MockEvent",
            "fields": [{"name": "id", "type": "string"}],
        },
    )
    payload: dict[str, Any] = {
        "schemaType": "AVRO",
        "schema": schema,
    }
    return json.dumps(payload).encode("utf-8")


def schema_id_path(schema_id: int) -> str:
    return f"/schemas/ids/{schema_id}"


def http_get_cold(host: str, port: int, path: str) -> None:
    """One-shot GET: new TCP connection per call (cold / empty-cache proxy)."""

    conn = HTTPConnection(host, port, timeout=60)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        if resp.status != 200:
            raise RuntimeError(f"mock registry HTTP {resp.status}")
        resp.read()
    finally:
        conn.close()


class MockRegistryServer:
    """
    Loopback HTTP server (threaded) implementing Confluent-style schema-by-id GET.

    Not a full SR; sufficient to time fetch-by-id cold vs keep-alive warm paths.
    """

    host = "127.0.0.1"

    def __init__(self) -> None:
        self.port: int = 0
        self.schema_id: int = 1
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @classmethod
    def start(cls, *, schema_id: int = 1) -> MockRegistryServer:
        body = confluent_schema_response_body()
        expected = schema_id_path(schema_id)

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path_only = self.path.split("?", 1)[0].rstrip("/")
                exp = expected.rstrip("/")
                if path_only == exp:
                    self.send_response(200)
                    self.send_header(
                        "Content-Type",
                        "application/vnd.schemaregistry.v1+json",
                    )
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_error(404)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        inst = cls()
        inst.schema_id = schema_id
        inst._httpd = ThreadingHTTPServer((inst.host, 0), _Handler)
        inst.port = int(inst._httpd.server_address[1])
        inst._thread = threading.Thread(
            target=inst._httpd.serve_forever,
            name="mock-sr",
            daemon=True,
        )
        inst._thread.start()
        return inst

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=10.0)


def prime_connection(conn: HTTPConnection, path: str) -> None:
    """One GET to establish TCP + first response (warmup, not timed)."""

    conn.request("GET", path)
    resp = conn.getresponse()
    if resp.status != 200:
        raise RuntimeError(f"mock registry HTTP {resp.status}")
    resp.read()


def http_get_on_connection(conn: HTTPConnection, path: str) -> None:
    conn.request("GET", path)
    resp = conn.getresponse()
    if resp.status != 200:
        raise RuntimeError(f"mock registry HTTP {resp.status}")
    resp.read()
