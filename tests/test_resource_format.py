from rlm_research_planner.services.resource_format import format_resource_amount


def test_resource_amount_supports_exact_and_short_display() -> None:
    assert format_resource_amount(1_234_567, "exact") == "1,234,567"
    assert format_resource_amount(999, "short") == "999"
    assert format_resource_amount(1_000, "short") == "1K"
    assert format_resource_amount(142_710, "short") == "142K"
    assert format_resource_amount(999_999, "short") == "999K"
    assert format_resource_amount(1_234_567, "short") == "1.23M"
    assert format_resource_amount(4_975_911, "short") == "4.97M"
