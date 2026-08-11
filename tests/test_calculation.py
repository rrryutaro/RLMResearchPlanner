from __future__ import annotations

from decimal import Decimal

import pytest

from rlm_research_planner.services.calculation import (
    GuildHelpPolicy,
    RoundingMode,
    VIP_FREE_SPEEDUP_MINUTES,
    apply_free_speedup_time,
    apply_guild_helps,
    apply_research_speed,
    free_speedup_seconds_for_vip,
    format_duration,
    vip_level_for_free_speedup_seconds,
)


def test_research_speed_zero_percent() -> None:
    assert apply_research_speed(1000, 0) == 1000


def test_research_speed_one_hundred_percent() -> None:
    assert apply_research_speed(1000, 100) == 500


def test_research_speed_decimal_and_rounding_modes() -> None:
    assert apply_research_speed(1000, 12.5, RoundingMode.CEILING) == 889
    assert apply_research_speed(1000, 12.5, RoundingMode.FLOOR) == 888
    assert apply_research_speed(1000, 12.5, RoundingMode.NEAREST) == 889


def test_free_speedup_time_is_deducted_after_research_speed() -> None:
    adjusted = apply_research_speed(473_040, 224.84)
    assert adjusted == 145_623
    assert apply_free_speedup_time(adjusted, 100 * 60) == 139_623


def test_free_speedup_time_does_not_produce_negative_time() -> None:
    assert apply_free_speedup_time(30, 60) == 0


def test_every_vip_level_maps_to_its_free_speedup_time() -> None:
    assert VIP_FREE_SPEEDUP_MINUTES == {
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
    assert {
        level: free_speedup_seconds_for_vip(level) // 60
        for level in range(1, 16)
    } == VIP_FREE_SPEEDUP_MINUTES


def test_legacy_free_speedup_time_migrates_to_the_nearest_vip_level() -> None:
    assert vip_level_for_free_speedup_seconds(100 * 60) == 11
    assert vip_level_for_free_speedup_seconds(149 * 60) == 15


def test_duration_uses_the_same_clock_style_as_the_game() -> None:
    assert format_duration(139_623) == "1d 14:47:03"
    assert format_duration(7 * 3600 + 5 * 60 + 32) == "07:05:32"
    assert format_duration(0) == "00:00:00"


def test_guild_help_zero() -> None:
    assert apply_guild_helps(10000, 0) == 10000


def test_guild_help_one_uses_one_percent() -> None:
    assert apply_guild_helps(10000, 1) == 9900


def test_guild_help_thirty_is_applied_sequentially() -> None:
    result = apply_guild_helps(10000, 30)
    assert 7300 < result < 7500
    assert result != 7000


def test_minimum_one_minute_applies_when_one_percent_is_smaller() -> None:
    assert apply_guild_helps(5000, 1) == 4940


def test_remaining_less_than_one_minute_reaches_zero() -> None:
    assert apply_guild_helps(30, 1) == 0


def test_help_rounding_is_configurable() -> None:
    policy = GuildHelpPolicy(
        reduction_rate=Decimal("0.013"),
        minimum_reduction_seconds=0,
        rounding=RoundingMode.FLOOR,
    )
    assert apply_guild_helps(101, 1, policy) == 99


@pytest.mark.parametrize("value", [-1, -100])
def test_negative_values_are_rejected(value: int) -> None:
    with pytest.raises(ValueError):
        apply_research_speed(value, 0)
    with pytest.raises(ValueError):
        apply_guild_helps(100, value)
    with pytest.raises(ValueError):
        apply_free_speedup_time(100, value)
