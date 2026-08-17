from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from enum import Enum


class RoundingMode(str, Enum):
    CEILING = "ceiling"
    FLOOR = "floor"
    NEAREST = "nearest"


EVENT_DISCOUNTABLE_RESEARCH_RESOURCE_KEYS = frozenset(
    {"food", "stone", "timber", "ore", "gold"}
)


ROUNDING_MAP = {
    RoundingMode.CEILING: ROUND_CEILING,
    RoundingMode.FLOOR: ROUND_FLOOR,
    RoundingMode.NEAREST: ROUND_HALF_UP,
}

VIP_FREE_SPEEDUP_MINUTES = {
    1: 10,
    2: 24,
    3: 26,
    4: 30,
    5: 40,
    6: 50,
    7: 60,
    8: 70,
    9: 80,
    10: 90,
    11: 100,
    12: 110,
    13: 120,
    14: 130,
    15: 150,
}


@dataclass(frozen=True)
class GuildHelpPolicy:
    reduction_rate: Decimal = Decimal("0.01")
    minimum_reduction_seconds: int = 60
    rounding: RoundingMode = RoundingMode.CEILING


def _round_seconds(value: Decimal, mode: RoundingMode) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUNDING_MAP[mode]))


def apply_research_speed(
    base_seconds: int,
    speed_percent: float | Decimal,
    rounding: RoundingMode = RoundingMode.CEILING,
) -> int:
    if base_seconds < 0:
        raise ValueError("base_seconds must be non-negative")
    speed = Decimal(str(speed_percent))
    if speed < 0:
        raise ValueError("speed_percent must be non-negative")
    adjusted = Decimal(base_seconds) / (Decimal("1") + speed / Decimal("100"))
    return max(0, _round_seconds(adjusted, rounding))


def apply_percentage_discount(
    value: int,
    discount_percent: float | Decimal,
) -> int:
    """Apply an in-game percentage cut before speed modifiers.

    Event research discounts are shown as cuts to the original time and costs.
    The game drops the fractional remainder before applying research speed.
    """

    if value < 0:
        raise ValueError("value must be non-negative")
    discount = Decimal(str(discount_percent))
    if discount < 0 or discount > 100:
        raise ValueError("discount_percent must be between 0 and 100")
    remaining = Decimal(value) * (Decimal("1") - discount / Decimal("100"))
    return max(0, _round_seconds(remaining, RoundingMode.FLOOR))


def apply_research_event_resource_discount(
    resource_id: str,
    value: int,
    discount_percent: float | Decimal,
) -> int:
    if resource_id not in EVENT_DISCOUNTABLE_RESEARCH_RESOURCE_KEYS:
        return value
    return apply_percentage_discount(value, discount_percent)


def apply_free_speedup_time(
    initial_seconds: int,
    free_speedup_seconds: int,
) -> int:
    if initial_seconds < 0:
        raise ValueError("initial_seconds must be non-negative")
    if free_speedup_seconds < 0:
        raise ValueError("free_speedup_seconds must be non-negative")
    return max(0, initial_seconds - free_speedup_seconds)


def free_speedup_seconds_for_vip(vip_level: int) -> int:
    normalized = max(1, min(15, int(vip_level)))
    return VIP_FREE_SPEEDUP_MINUTES[normalized] * 60


def vip_level_for_free_speedup_seconds(free_speedup_seconds: int) -> int:
    seconds = max(0, int(free_speedup_seconds))
    return min(
        VIP_FREE_SPEEDUP_MINUTES,
        key=lambda level: (
            abs(VIP_FREE_SPEEDUP_MINUTES[level] * 60 - seconds),
            level,
        ),
    )


def apply_guild_helps(
    initial_seconds: int,
    help_count: int,
    policy: GuildHelpPolicy | None = None,
) -> int:
    """Estimate the shortest remaining timer after consecutive guild helps.

    Each help is applied to the remaining timer after the previous help.  Calling
    this with the timer shown when a project starts therefore models receiving
    every configured help immediately, before ordinary elapsed time can reduce
    the value on which the percentage is calculated.
    """
    if initial_seconds < 0:
        raise ValueError("initial_seconds must be non-negative")
    if help_count < 0:
        raise ValueError("help_count must be non-negative")
    active_policy = policy or GuildHelpPolicy()
    remaining = Decimal(initial_seconds)
    minimum = Decimal(active_policy.minimum_reduction_seconds)
    for _ in range(help_count):
        if remaining <= 0:
            break
        proportional = remaining * active_policy.reduction_rate
        reduction = max(proportional, minimum)
        remaining = max(Decimal("0"), remaining - reduction)
        remaining = Decimal(_round_seconds(remaining, active_policy.rounding))
    return int(remaining)


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
    return f"{hours:02}:{minutes:02}:{seconds:02}"
