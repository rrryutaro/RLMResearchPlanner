from __future__ import annotations


def format_resource_amount(amount: int, mode: str = "exact") -> str:
    value = int(amount)
    if mode != "short" or abs(value) < 1_000:
        return f"{value:,}"

    for divisor, suffix in (
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ):
        if abs(value) >= divisor:
            hundredths = abs(value) * 100 // divisor
            shortened = hundredths / 100
            if value < 0:
                shortened = -shortened
            return f"{shortened:.2f}".rstrip("0").rstrip(".") + suffix
    return f"{value:,}"
