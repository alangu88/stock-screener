"""Small numeric helpers shared across the scoring and sizing layers."""

from __future__ import annotations

import math


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def is_nan(value: object) -> bool:
    return isinstance(value, float) and math.isnan(value)
