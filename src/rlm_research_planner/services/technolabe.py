from __future__ import annotations

import math


# Use 33d 04:00:00 of original (pre-research-speed) time as the 100% efficiency
# benchmark. Sourced per-level counts always take precedence because the game
# assigns item counts per research rather than exposing a universal formula.
TECHNOLABE_CAPACITY_SECONDS = 33 * 86_400 + 4 * 3_600


def technolabe_usage(
    base_time_seconds: int | None,
    sourced_count: int | None = None,
) -> tuple[int | None, float | None]:
    if base_time_seconds is None:
        return None, None
    base_time = max(0, int(base_time_seconds))
    if base_time == 0:
        return 0, None
    count = (
        max(1, int(sourced_count))
        if sourced_count is not None and int(sourced_count) > 0
        else max(1, math.ceil(base_time / TECHNOLABE_CAPACITY_SECONDS))
    )
    efficiency = min(
        100.0,
        base_time / (count * TECHNOLABE_CAPACITY_SECONDS) * 100.0,
    )
    return count, efficiency


def technolabe_efficiency(
    total_base_seconds: int,
    total_count: int,
) -> float | None:
    if total_base_seconds <= 0 or total_count <= 0:
        return None
    return min(
        100.0,
        total_base_seconds
        / (total_count * TECHNOLABE_CAPACITY_SECONDS)
        * 100.0,
    )
