from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import ceil, gcd
from typing import Iterable

from rlm_research_planner.domain.models import (
    PaidItem,
    PaidOffer,
    SpeedupInventoryItem,
)
from rlm_research_planner.services.paid_value import (
    minimum_gems_for_speedup_seconds,
)


SPEEDUP_KINDS = (
    "general",
    "research",
    "training",
    "construction",
    "healing",
    "merging",
    "crafting",
)


@dataclass(frozen=True)
class SpeedupCoverage:
    target_kind: str
    required_seconds: int
    available_seconds: int
    applied_seconds: int
    remaining_seconds: int
    surplus_seconds: int
    remaining_task_seconds: tuple[int, ...] = ()
    used_items: tuple[SpeedupInventoryItem, ...] = ()


@dataclass(frozen=True)
class PaidOfferRecommendation:
    offer_id: str
    title: str
    purchases: int
    seconds_per_purchase: int
    total_seconds: int
    diamond_cost_each: int
    total_diamond_cost: int | None
    gems_per_purchase: int
    available_gems: int
    applied_speedup_seconds: int
    gems_used: int
    gem_applied_seconds: int
    remaining_seconds: int
    excess_seconds: int


def normalize_speedup_inventory(
    entries: Iterable[SpeedupInventoryItem],
) -> tuple[SpeedupInventoryItem, ...]:
    totals: dict[tuple[str, int], int] = {}
    for entry in entries:
        kind = str(entry.kind).strip()
        duration = max(0, int(entry.duration_seconds))
        quantity = max(0, int(entry.quantity))
        if kind not in SPEEDUP_KINDS or duration <= 0 or quantity <= 0:
            continue
        key = (kind, duration)
        totals[key] = totals.get(key, 0) + quantity
    order = {kind: index for index, kind in enumerate(SPEEDUP_KINDS)}
    return tuple(
        SpeedupInventoryItem(kind, duration, quantity)
        for (kind, duration), quantity in sorted(
            totals.items(),
            key=lambda item: (order[item[0][0]], -item[0][1]),
        )
    )


def applicable_speedup_seconds(
    entries: Iterable[SpeedupInventoryItem],
    target_kind: str,
) -> int:
    eligible = {"general", target_kind}
    return sum(
        max(0, int(entry.duration_seconds)) * max(0, int(entry.quantity))
        for entry in entries
        if entry.kind in eligible
    )


def _normalized_task_seconds(
    required_seconds: int,
    task_seconds: Iterable[int] | None,
) -> list[int]:
    required = max(0, int(required_seconds))
    if task_seconds is None:
        return [required] if required else []
    tasks = [max(0, int(value)) for value in task_seconds if int(value) > 0]
    known_total = sum(tasks)
    if known_total < required:
        tasks.append(required - known_total)
    return tasks


def _allocate_without_overrun(
    entries: Iterable[SpeedupInventoryItem],
    target_kind: str,
    task_seconds: Iterable[int],
) -> tuple[tuple[int, ...], tuple[SpeedupInventoryItem, ...]]:
    remaining = [max(0, int(value)) for value in task_seconds if int(value) > 0]
    eligible = {"general", target_kind}
    candidates = list(
        sorted(
            (
                entry
                for entry in normalize_speedup_inventory(entries)
                if entry.kind in eligible
            ),
            key=lambda entry: (
                -entry.duration_seconds,
                entry.kind == "general",
            ),
        )
    )
    # A duration can never be used more often than the sum of the per-task
    # capacities.  Paid-offer simulations may multiply an offer thousands of
    # times while looking for a completing purchase count; retaining those
    # impossible excess quantities makes the subset solver needlessly huge.
    quantities = [
        min(
            max(0, int(entry.quantity)),
            sum(task // entry.duration_seconds for task in remaining),
        )
        for entry in candidates
    ]
    used_quantities = [0] * len(candidates)

    for task_index in sorted(range(len(remaining)), key=remaining.__getitem__):
        task = remaining[task_index]
        available_indexes = [
            index
            for index, entry in enumerate(candidates)
            if quantities[index] > 0 and 0 < entry.duration_seconds <= task
        ]
        if not available_indexes:
            continue
        scale = 0
        for index in available_indexes:
            scale = gcd(scale, candidates[index].duration_seconds)
        capacity = task // max(1, scale)
        chunks: list[tuple[int, int, int]] = []
        for index in available_indexes:
            remaining_quantity = quantities[index]
            chunk_quantity = 1
            unit = candidates[index].duration_seconds // scale
            while remaining_quantity > 0:
                count = min(chunk_quantity, remaining_quantity)
                chunks.append((index, count, unit * count))
                remaining_quantity -= count
                chunk_quantity *= 2

        selected_counts: dict[int, int] = {}
        if capacity <= 2_000_000:
            mask = (1 << (capacity + 1)) - 1
            reachable = 1
            newly_reachable: list[int] = []
            for _index, _count, weight in chunks:
                new_states = ((reachable << weight) & mask) & ~reachable
                newly_reachable.append(new_states)
                reachable |= new_states
            target = reachable.bit_length() - 1
            selected = target
            for chunk_index in range(len(chunks) - 1, -1, -1):
                if (newly_reachable[chunk_index] >> selected) & 1:
                    entry_index, count, weight = chunks[chunk_index]
                    selected_counts[entry_index] = (
                        selected_counts.get(entry_index, 0) + count
                    )
                    selected -= weight
            applied = target * scale
        else:
            applied = 0
            for index in available_indexes:
                duration = candidates[index].duration_seconds
                count = min(quantities[index], (task - applied) // duration)
                if count > 0:
                    selected_counts[index] = count
                    applied += duration * count

        remaining[task_index] -= applied
        for index, count in selected_counts.items():
            quantities[index] -= count
            used_quantities[index] += count

    used = tuple(
        SpeedupInventoryItem(entry.kind, entry.duration_seconds, count)
        for entry, count in zip(candidates, used_quantities, strict=True)
        if count > 0
    )
    return tuple(remaining), used


@lru_cache(maxsize=4096)
def _unlimited_exact_duration(
    seconds: int,
    durations: tuple[int, ...],
) -> bool:
    """Whether unlimited items can fill one task without exceeding it.

    This inexpensive feasibility gate prevents paid-offer recommendation from
    repeatedly running the bounded allocator when no number of purchases can
    ever fill a task exactly (for example, only five-minute items for a timer
    with a non-five-minute remainder).
    """

    target = max(0, int(seconds))
    normalized = tuple(sorted({max(0, int(value)) for value in durations} - {0}))
    if target <= 0:
        return True
    if not normalized:
        return False
    scale = 0
    for duration in normalized:
        scale = gcd(scale, duration)
    scale = max(1, scale)
    if target % scale:
        return False
    target //= scale
    units = tuple(duration // scale for duration in normalized)
    if 1 in units:
        return True
    reachable = bytearray(target + 1)
    reachable[0] = 1
    for value in range(target + 1):
        if not reachable[value]:
            continue
        for unit in units:
            next_value = value + unit
            if next_value <= target:
                reachable[next_value] = 1
    return bool(reachable[target])


def speedup_coverage(
    required_seconds: int,
    entries: Iterable[SpeedupInventoryItem],
    target_kind: str,
    task_seconds: Iterable[int] | None = None,
) -> SpeedupCoverage:
    tasks = _normalized_task_seconds(required_seconds, task_seconds)
    required = sum(tasks)
    normalized_entries = normalize_speedup_inventory(entries)
    available = applicable_speedup_seconds(normalized_entries, target_kind)
    remaining_tasks, used_items = _allocate_without_overrun(
        normalized_entries,
        target_kind,
        tasks,
    )
    remaining = sum(remaining_tasks)
    applied = max(0, required - remaining)
    return SpeedupCoverage(
        target_kind=target_kind,
        required_seconds=required,
        available_seconds=available,
        applied_seconds=applied,
        remaining_seconds=remaining,
        surplus_seconds=max(0, available - applied),
        remaining_task_seconds=remaining_tasks,
        used_items=used_items,
    )


def add_paid_items_to_inventory(
    entries: Iterable[SpeedupInventoryItem],
    paid_items: Iterable[PaidItem],
) -> tuple[SpeedupInventoryItem, ...]:
    additions = [
        SpeedupInventoryItem(
            kind=item.kind,
            duration_seconds=max(0, int(item.duration_seconds)),
            quantity=max(0, int(item.quantity)),
        )
        for item in paid_items
        if item.kind in SPEEDUP_KINDS
    ]
    return normalize_speedup_inventory((*entries, *additions))


def paid_offer_speedup_seconds(offer: PaidOffer, target_kind: str) -> int:
    eligible = {"general", target_kind}
    return sum(
        max(0, int(item.duration_seconds)) * max(0, int(item.quantity))
        for item in offer.items
        if item.kind in eligible
    )


def paid_offer_gems(offer: PaidOffer) -> int:
    return (
        max(0, int(offer.included_gems))
        + max(0, int(offer.bonus_gems))
        + sum(
            max(0, int(item.quantity))
            for item in offer.items
            if item.kind == "gems"
        )
    )


def _offer_covers_shortfall(
    shortfall_seconds: int,
    offer: PaidOffer,
    target_kind: str,
    gems_per_purchase: int,
    purchases: int,
    task_seconds: tuple[int, ...],
    use_gems: bool,
) -> bool:
    repeated_items = tuple(
        PaidItem(
            kind=item.kind,
            name=item.name,
            quantity=max(0, int(item.quantity)) * purchases,
            duration_seconds=item.duration_seconds,
            gem_value_each=item.gem_value_each,
            points_each=item.points_each,
        )
        for item in offer.items
    )
    coverage = speedup_coverage(
        shortfall_seconds,
        (
            SpeedupInventoryItem(
                item.kind,
                max(0, int(item.duration_seconds)),
                max(0, int(item.quantity)),
            )
            for item in repeated_items
            if item.kind in SPEEDUP_KINDS
        ),
        target_kind,
        task_seconds,
    )
    if coverage.remaining_seconds <= 0:
        return True
    if not use_gems or gems_per_purchase <= 0:
        return False
    required_gems = sum(
        minimum_gems_for_speedup_seconds(seconds).gems
        for seconds in coverage.remaining_task_seconds
    )
    return gems_per_purchase * purchases >= required_gems


def _minimum_offer_purchases(
    shortfall_seconds: int,
    offer: PaidOffer,
    target_kind: str,
    gems_per_purchase: int,
    task_seconds: tuple[int, ...],
    use_gems: bool,
) -> int | None:
    eligible_durations = [
        max(0, int(item.duration_seconds))
        for item in offer.items
        if item.kind in {"general", target_kind}
        and int(item.duration_seconds) > 0
        and int(item.quantity) > 0
    ]
    if (
        (not use_gems or gems_per_purchase <= 0)
        and eligible_durations
        and any(
            not _unlimited_exact_duration(seconds, tuple(eligible_durations))
            for seconds in task_seconds
        )
    ):
        return None
    if use_gems and gems_per_purchase > 0:
        gems_without_speedups = sum(
            minimum_gems_for_speedup_seconds(seconds).gems
            for seconds in task_seconds
        )
        high = max(1, ceil(gems_without_speedups / gems_per_purchase))
    elif eligible_durations:
        minimum_duration = min(eligible_durations)
        high = max(
            1,
            sum(ceil(seconds / minimum_duration) for seconds in task_seconds),
        )
    else:
        return None
    if not _offer_covers_shortfall(
        shortfall_seconds,
        offer,
        target_kind,
        gems_per_purchase,
        high,
        task_seconds,
        use_gems,
    ):
        return None
    low = 1
    while low < high:
        middle = (low + high) // 2
        if _offer_covers_shortfall(
            shortfall_seconds,
            offer,
            target_kind,
            gems_per_purchase,
            middle,
            task_seconds,
            use_gems,
        ):
            high = middle
        else:
            low = middle + 1
    return low


def recommend_paid_offers(
    shortfall_seconds: int,
    offers: Iterable[PaidOffer],
    target_kind: str,
    *,
    limit: int = 3,
    task_seconds: Iterable[int] | None = None,
    use_gems: bool = False,
) -> tuple[PaidOfferRecommendation, ...]:
    tasks = tuple(_normalized_task_seconds(shortfall_seconds, task_seconds))
    shortfall = sum(tasks)
    if shortfall <= 0:
        return ()
    recommendations: list[PaidOfferRecommendation] = []
    for offer in offers:
        seconds = paid_offer_speedup_seconds(offer, target_kind)
        gems = paid_offer_gems(offer)
        if seconds <= 0 and (not use_gems or gems <= 0):
            continue
        purchases = _minimum_offer_purchases(
            shortfall,
            offer,
            target_kind,
            gems,
            tasks,
            use_gems,
        )
        # A saved offer is still useful even when repeated purchases cannot
        # finish every task without wasting a speed-up item.  In that case,
        # show the contribution from one purchase and the remaining time
        # instead of hiding the offer entirely.
        if purchases is None:
            purchases = 1
        total_seconds = seconds * purchases
        available_gems = gems * purchases
        repeated_inventory = tuple(
            SpeedupInventoryItem(
                item.kind,
                max(0, int(item.duration_seconds)),
                max(0, int(item.quantity)) * purchases,
            )
            for item in offer.items
            if item.kind in SPEEDUP_KINDS
        )
        coverage = speedup_coverage(
            shortfall,
            repeated_inventory,
            target_kind,
            tasks,
        )
        gem_purchases = tuple(
            minimum_gems_for_speedup_seconds(value)
            for value in coverage.remaining_task_seconds
        )
        required_gems = sum(item.gems for item in gem_purchases)
        can_use_gems = (
            use_gems
            and coverage.remaining_seconds > 0
            and available_gems >= required_gems
        )
        if coverage.applied_seconds <= 0 and not can_use_gems:
            continue
        gems_used = required_gems if can_use_gems else 0
        gem_applied_seconds = coverage.remaining_seconds if can_use_gems else 0
        remaining_seconds = max(
            0,
            coverage.remaining_seconds - gem_applied_seconds,
        )
        cost_each = max(0, int(offer.diamond_cost))
        recommendations.append(
            PaidOfferRecommendation(
                offer_id=offer.offer_id,
                title=offer.title,
                purchases=purchases,
                seconds_per_purchase=seconds,
                total_seconds=total_seconds,
                diamond_cost_each=cost_each,
                total_diamond_cost=(cost_each * purchases if cost_each else None),
                gems_per_purchase=gems,
                available_gems=available_gems,
                applied_speedup_seconds=coverage.applied_seconds,
                gems_used=gems_used,
                gem_applied_seconds=gem_applied_seconds,
                remaining_seconds=remaining_seconds,
                excess_seconds=max(
                    0,
                    coverage.surplus_seconds
                    + sum(item.purchased_seconds for item in gem_purchases)
                    - gem_applied_seconds,
                ),
            )
        )
    recommendations.sort(
        key=lambda item: (
            item.remaining_seconds > 0,
            item.total_diamond_cost is None,
            item.total_diamond_cost if item.total_diamond_cost is not None else 0,
            item.excess_seconds,
            item.purchases,
            item.title.casefold(),
        )
    )
    return tuple(recommendations[: max(0, int(limit))])
