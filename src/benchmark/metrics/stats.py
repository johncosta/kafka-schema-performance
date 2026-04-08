from __future__ import annotations


def _percentile(sorted_samples: list[float], q: float) -> float:
    if not sorted_samples:
        return float("nan")
    n = len(sorted_samples)
    idx = (n - 1) * q
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    w = idx - lo
    return sorted_samples[lo] * (1.0 - w) + sorted_samples[hi] * w


def summarize_times(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {
            "p50_s": float("nan"),
            "p90_s": float("nan"),
            "p99_s": float("nan"),
            "mean_s": float("nan"),
            "records_per_s": 0.0,
        }
    s = sorted(samples)
    mean = sum(samples) / len(samples)
    inv_mean = 1.0 / mean if mean > 0 else float("inf")
    return {
        "p50_s": _percentile(s, 0.50),
        "p90_s": _percentile(s, 0.90),
        "p99_s": _percentile(s, 0.99),
        "mean_s": mean,
        "records_per_s": inv_mean,
    }


def mb_per_second(mean_s: float, size_bytes: int) -> float:
    if mean_s <= 0:
        return float("nan")
    return (size_bytes / mean_s) / (1024.0 * 1024.0)
