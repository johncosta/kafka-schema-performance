from __future__ import annotations

import random
from enum import StrEnum

from benchmark.models.event import AnalyticsEvent, EventContext


class PayloadProfile(StrEnum):
    small = "small"
    medium = "medium"
    large = "large"
    evolution = "evolution"


def sample_event(profile: PayloadProfile, seed: int) -> AnalyticsEvent:
    """Deterministic pseudo-realistic record for the given profile."""

    rng = random.Random(seed)
    event_id = f"{rng.getrandbits(64):016x}"
    user_id = f"user_{rng.randint(0, 10_000_000)}"
    ts_ms = rng.randint(1_700_000_000_000, 1_750_000_000_000)
    props = {f"k{i}": f"v{rng.randint(0, 1_000_000)}" for i in range(8)}

    if profile is PayloadProfile.small:
        return AnalyticsEvent(
            event_id=event_id,
            ts_ms=ts_ms,
            user_id=user_id,
            props=props,
        )
    if profile is PayloadProfile.medium:
        context = EventContext(
            device_id=f"dev_{rng.getrandbits(32):x}",
            session_id=f"sess_{rng.getrandbits(48):x}",
            tags=tuple(f"t{j}" for j in range(rng.randint(4, 14))),
        )
        return AnalyticsEvent(
            event_id=event_id,
            ts_ms=ts_ms,
            user_id=user_id,
            props=props,
            context=context,
        )
    if profile is PayloadProfile.large:
        context = EventContext(
            device_id="dev_large",
            session_id="sess_large",
            tags=("t1", "t2", "t3"),
        )
        payload_blob = rng.randbytes(100_000)
        return AnalyticsEvent(
            event_id=event_id,
            ts_ms=ts_ms,
            user_id=user_id,
            props=props,
            context=context,
            payload_blob=payload_blob,
        )
    # evolution: same shape as small; Avro uses v1 writer without new_field
    return AnalyticsEvent(
        event_id=event_id,
        ts_ms=ts_ms,
        user_id=user_id,
        props=props,
        new_field=None,
    )


def golden_small_event() -> AnalyticsEvent:
    """Fixed record for unit tests."""

    return AnalyticsEvent(
        event_id="01hz8x3n0testev3nt1d",
        ts_ms=1_704_067_200_000,
        user_id="user_golden",
        props={"region": "us-east", "plan": "pro"},
    )


def golden_medium_event() -> AnalyticsEvent:
    """Fixed nested record (~2–10 KB class) for cross-codec regression tests."""

    return AnalyticsEvent(
        event_id="01hz8x3n0med1umev3nt1d",
        ts_ms=1_704_067_200_001,
        user_id="user_golden_medium",
        props={"region": "eu-west", "tier": "gold", "sku": "abc-123"},
        context=EventContext(
            device_id="dev_golden_9f2a",
            session_id="sess_golden_bee1",
            tags=("alpha", "beta", "gamma", "delta"),
        ),
    )


def _golden_large_payload_blob() -> bytes:
    """Deterministic 100 KiB blob (PRD large / blob-heavy profile)."""

    chunk = bytes(range(256))
    return chunk * 390 + chunk[:160]


def golden_large_event() -> AnalyticsEvent:
    """Fixed blob-heavy record for size and allocation regression tests."""

    return AnalyticsEvent(
        event_id="01hz8x3n0largeev3nt1d",
        ts_ms=1_704_067_200_002,
        user_id="user_golden_large",
        props={f"k{i}": f"v{i:04d}" for i in range(16)},
        context=EventContext(
            device_id="dev_large_golden",
            session_id="sess_large_golden",
            tags=("t1", "t2"),
        ),
        payload_blob=_golden_large_payload_blob(),
    )


def golden_evolution_event() -> AnalyticsEvent:
    """Logical same as small; optional ``new_field`` unset (writer may omit)."""

    return AnalyticsEvent(
        event_id="01hz8x3n0ev0lut10n1d",
        ts_ms=1_704_067_200_003,
        user_id="user_golden_evo",
        props={"k0": "v0"},
        new_field=None,
    )


def sample_events(
    profile: PayloadProfile,
    seed: int,
    count: int,
) -> list[AnalyticsEvent]:
    """Return ``count`` records: ``sample_event(profile, seed+i)`` for each ``i``."""

    if count < 0:
        raise ValueError("count must be >= 0")
    return [sample_event(profile, seed + i) for i in range(count)]
