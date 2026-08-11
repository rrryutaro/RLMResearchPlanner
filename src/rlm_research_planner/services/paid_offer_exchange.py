from __future__ import annotations

from datetime import datetime, timezone

from rlm_research_planner.domain.models import PaidItem, PaidOffer, PaidValuation
from rlm_research_planner.services.paid_value import PAID_GOALS, PAID_ITEM_KINDS


DOCUMENT_TYPE = "RLMResearchPlanner.paid-offers"
SCHEMA_VERSION = 1


class PaidOfferExchangeError(ValueError):
    pass


def paid_offer_exchange_payload(
    offers: list[PaidOffer] | tuple[PaidOffer, ...],
    valuation: PaidValuation,
    *,
    name: str = "",
) -> dict[str, object]:
    return {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "name": name.strip()[:200],
        "valuation": {
            "points_per_gem": valuation.points_per_gem,
            "general_speedup_points_per_hour": valuation.general_speedup_points_per_hour,
            "research_speedup_points_per_hour": valuation.research_speedup_points_per_hour,
            "training_speedup_points_per_hour": valuation.training_speedup_points_per_hour,
            "construction_speedup_points_per_hour": valuation.construction_speedup_points_per_hour,
            "healing_speedup_points_per_hour": valuation.healing_speedup_points_per_hour,
            "merging_speedup_points_per_hour": valuation.merging_speedup_points_per_hour,
            "crafting_speedup_points_per_hour": valuation.crafting_speedup_points_per_hour,
            "use_speedup_gem_presets": valuation.use_speedup_gem_presets,
        },
        "offers": [
            {
                "offer_id": offer.offer_id,
                "title": offer.title,
                "goal": offer.goal,
                "memo": offer.memo,
                "diamond_cost": offer.diamond_cost,
                "included_gems": offer.included_gems,
                "bonus_gems": offer.bonus_gems,
                "items": [
                    {
                        "kind": item.kind,
                        "name": item.name,
                        "quantity": item.quantity,
                        "duration_seconds": item.duration_seconds,
                        "gem_value_each": item.gem_value_each,
                        "points_each": item.points_each,
                    }
                    for item in offer.items
                ],
                "created_at": offer.created_at,
                "updated_at": offer.updated_at,
            }
            for offer in offers
        ],
    }


def paid_offers_from_exchange_payload(
    raw: object,
) -> tuple[tuple[PaidOffer, ...], PaidValuation, str]:
    if not isinstance(raw, dict):
        raise PaidOfferExchangeError("Invalid paid-offer document")
    if raw.get("document_type") != DOCUMENT_TYPE or raw.get("schema_version") != 1:
        raise PaidOfferExchangeError("Unsupported paid-offer document")
    raw_offers = raw.get("offers")
    if not isinstance(raw_offers, list):
        raise PaidOfferExchangeError("The paid-offer list is missing")

    offers: list[PaidOffer] = []
    for index, value in enumerate(raw_offers):
        if not isinstance(value, dict):
            continue
        offer_id = str(value.get("offer_id", "")).strip() or f"imported-{index + 1}"
        title = str(value.get("title", "")).strip()
        if not title:
            continue
        items: list[PaidItem] = []
        for raw_item in value.get("items", []):
            if not isinstance(raw_item, dict):
                continue
            try:
                kind = str(raw_item.get("kind", "custom")).strip()
                items.append(
                    PaidItem(
                        kind=kind if kind in PAID_ITEM_KINDS else "custom",
                        name=str(raw_item.get("name", ""))[:200],
                        quantity=max(0, int(raw_item.get("quantity", 0))),
                        duration_seconds=max(0, int(raw_item.get("duration_seconds", 0))),
                        gem_value_each=max(0.0, float(raw_item.get("gem_value_each", 0))),
                        points_each=max(0.0, float(raw_item.get("points_each", 0))),
                    )
                )
            except (TypeError, ValueError):
                continue
        try:
            goal = str(value.get("goal", "all_round")).strip()
            offers.append(
                PaidOffer(
                    offer_id=offer_id[:100],
                    title=title[:200],
                    goal=goal if goal in PAID_GOALS else "all_round",
                    memo=str(value.get("memo", ""))[:2000],
                    diamond_cost=max(0, int(value.get("diamond_cost", 0))),
                    included_gems=max(0, int(value.get("included_gems", 0))),
                    bonus_gems=max(0, int(value.get("bonus_gems", 0))),
                    items=tuple(items),
                    created_at=str(value.get("created_at", "")),
                    updated_at=str(value.get("updated_at", "")),
                )
            )
        except (TypeError, ValueError):
            continue
    raw_valuation = raw.get("valuation")
    if not offers and not isinstance(raw_valuation, dict):
        raise PaidOfferExchangeError(
            "No valid paid offers or comparison settings were found"
        )
    value = raw_valuation if isinstance(raw_valuation, dict) else {}
    try:
        valuation = PaidValuation(
            points_per_gem=max(0.0, float(value.get("points_per_gem", 1))),
            general_speedup_points_per_hour=max(0.0, float(value.get("general_speedup_points_per_hour", 0))),
            research_speedup_points_per_hour=max(0.0, float(value.get("research_speedup_points_per_hour", 0))),
            training_speedup_points_per_hour=max(0.0, float(value.get("training_speedup_points_per_hour", 0))),
            construction_speedup_points_per_hour=max(0.0, float(value.get("construction_speedup_points_per_hour", 0))),
            healing_speedup_points_per_hour=max(0.0, float(value.get("healing_speedup_points_per_hour", 0))),
            merging_speedup_points_per_hour=max(0.0, float(value.get("merging_speedup_points_per_hour", 0))),
            crafting_speedup_points_per_hour=max(0.0, float(value.get("crafting_speedup_points_per_hour", 0))),
            use_speedup_gem_presets=bool(value.get("use_speedup_gem_presets", True)),
        )
    except (TypeError, ValueError):
        valuation = PaidValuation()
    return tuple(offers), valuation, str(raw.get("name", ""))[:200]
