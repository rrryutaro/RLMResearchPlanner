from __future__ import annotations

import math

# Use 33d 03:59:00 of original (pre-research-speed) time as the 100% efficiency
# benchmark. Sourced per-level counts always take precedence because the game
# assigns item counts per research rather than exposing a universal formula.
# In particular, Monster Hunt research can require more Technolabes than other
# research with a similar original duration.  Never infer an item count here.
TECHNOLABE_CAPACITY_SECONDS = 33 * 86_400 + 3 * 3_600 + 59 * 60


def is_technolabe_recommended(
    efficiency_percent: float | None,
    threshold_percent: float = 95.0,
) -> bool:
    """Return whether a known efficiency meets the player's recommendation line."""

    if efficiency_percent is None:
        return False
    efficiency = float(efficiency_percent)
    threshold = max(0.0, min(100.0, float(threshold_percent)))
    return math.isfinite(efficiency) and efficiency >= threshold


def technolabe_usage(
    base_time_seconds: int | None,
    sourced_count: int | None = None,
) -> tuple[int | None, float | None]:
    if base_time_seconds is None:
        return None, None
    base_time = max(0, int(base_time_seconds))
    if base_time == 0:
        return 0, None
    if sourced_count is None or int(sourced_count) <= 0:
        return None, None
    count = max(1, int(sourced_count))
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
