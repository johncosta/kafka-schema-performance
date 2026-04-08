from __future__ import annotations

import json
import time
from http.client import HTTPConnection

from benchmark.metrics.stats import summarize_times
from benchmark.registry_mock import (
    MockRegistryServer,
    http_get_cold,
    http_get_on_connection,
    prime_connection,
    schema_id_path,
)


def test_mock_registry_serves_schema_by_id() -> None:
    srv = MockRegistryServer.start(schema_id=7)
    try:
        path = schema_id_path(7)
        conn = HTTPConnection(srv.host, srv.port, timeout=10)
        try:
            prime_connection(conn, path)
            http_get_on_connection(conn, path)
        finally:
            conn.close()
    finally:
        srv.stop()


def test_mock_registry_json_parseable() -> None:
    srv = MockRegistryServer.start(schema_id=1)
    try:
        conn = HTTPConnection(srv.host, srv.port, timeout=10)
        try:
            conn.request("GET", schema_id_path(1))
            resp = conn.getresponse()
            assert resp.status == 200
            body = json.loads(resp.read().decode())
            assert "schema" in body
        finally:
            conn.close()
    finally:
        srv.stop()


def test_warm_fetch_not_slower_than_cold_by_orders_of_magnitude() -> None:
    """Heuristic: keep-alive loopback should not be drastically slower than cold."""

    srv = MockRegistryServer.start(schema_id=1)
    try:
        path = schema_id_path(1)
        n = 8
        cold = []
        for _ in range(n):
            t0 = time.perf_counter()
            http_get_cold(srv.host, srv.port, path)
            cold.append(time.perf_counter() - t0)
        warm = []
        wconn = HTTPConnection(srv.host, srv.port, timeout=10)
        try:
            prime_connection(wconn, path)
            for _ in range(n):
                t0 = time.perf_counter()
                http_get_on_connection(wconn, path)
                warm.append(time.perf_counter() - t0)
        finally:
            wconn.close()
        cold_m = summarize_times(cold)["mean_s"]
        warm_m = summarize_times(warm)["mean_s"]
        assert warm_m <= cold_m * 4.0
    finally:
        srv.stop()
