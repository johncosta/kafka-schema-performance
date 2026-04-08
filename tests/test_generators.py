from __future__ import annotations

import pytest

from benchmark.generate.records import (
    PayloadProfile,
    golden_large_event,
    sample_event,
    sample_events,
)


def test_sample_events_matches_individual_samples() -> None:
    profile = PayloadProfile.medium
    seed = 42
    n = 5
    assert sample_events(profile, seed, n) == [
        sample_event(profile, seed + i) for i in range(n)
    ]


def test_sample_events_empty() -> None:
    assert sample_events(PayloadProfile.small, 0, 0) == []


def test_sample_events_determinism() -> None:
    a = sample_events(PayloadProfile.large, 99, 3)
    b = sample_events(PayloadProfile.large, 99, 3)
    assert a == b
    assert len(a) == 3
    assert a[0] != a[1]


def test_sample_events_negative_count() -> None:
    with pytest.raises(ValueError, match="count"):
        sample_events(PayloadProfile.small, 0, -1)


def test_golden_large_payload_size() -> None:
    assert len(golden_large_event().payload_blob) == 100_000
