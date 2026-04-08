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
