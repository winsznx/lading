"""Paired statistics for arm-vs-FEFO comparisons."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

METRICS = ("spoiled_kg", "demand_filled_pct", "net_inr")
WIN = {"spoiled_kg": -1, "demand_filled_pct": 1, "net_inr": 1}


def describe(deltas: Sequence[float], metric: str) -> dict[str, float]:
    """Median, IQR bounds and win count of paired deltas (arm minus reference)."""
    arr = np.asarray(deltas, dtype=float)
    sign = WIN[metric]
    return {
        "median": round(float(np.median(arr)), 2),
        "q1": round(float(np.percentile(arr, 25)), 2),
        "q3": round(float(np.percentile(arr, 75)), 2),
        "wins": int(np.sum(arr * sign > 0)),
        "losses": int(np.sum(arr * sign < 0)),
        "n": int(arr.size),
    }


def summarise(rows: list[dict[str, Any]], arm: str) -> dict[str, dict[str, float]]:
    return {metric: describe([float(r["delta"][arm][metric]) for r in rows], metric) for metric in METRICS}
