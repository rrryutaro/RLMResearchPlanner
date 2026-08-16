from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rlm_research_planner.domain.observations import (
    ObservedResearchConnectionGroup,
    ObservedResearchEdge,
    ObservedResearchLevel,
    ObservedResearchNode,
    ObservedResearchRequirement,
    ResearchTreeObservation,
)


def _verification_status(
    level: Mapping[str, Any],
    tree: Mapping[str, Any],
) -> str:
    legacy_status = level.get("legacy_verification_status")
    if legacy_status:
        return str(legacy_status)
    verification = level.get("verification") or tree["default_verification"]
    return str(verification.get("status") or "provisional")


def _source_metadata(
    tree: Mapping[str, Any],
    sources_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[str, str, str]:
    verification = tree.get("default_verification")
    source_ids = (
        verification.get("source_ids", [])
        if isinstance(verification, Mapping)
        else []
    )
    source = next(
        (
            sources_by_id[str(source_id)]
            for source_id in source_ids
            if str(source_id) in sources_by_id
        ),
        {},
    )
    license_data = source.get("license")
    if not isinstance(license_data, Mapping):
        license_data = {}
    return (
        str(source.get("url") or ""),
        str(license_data.get("name") or ""),
        str(license_data.get("url") or ""),
    )


def observations_from_research_dataset(
    documents: Mapping[str, Any],
) -> tuple[ResearchTreeObservation, ...]:
    """Adapt a validated research dataset to the existing observation model.

    Phase 3 uses this exact function for legacy-equivalence comparison. A
    future runtime loader must reuse it instead of implementing a second
    interpretation of the dataset. The function does not select an application
    input path and therefore does not change the current runtime behavior.
    """

    manifest = documents["manifest"]
    locales = documents["locales"]
    trees = documents["trees"]
    raw_sources = documents["sources"].get("sources", [])
    sources_by_id = {
        str(source["id"]): source
        for source in raw_sources
        if isinstance(source, Mapping) and source.get("id")
    }
    observations: list[ResearchTreeObservation] = []
    for manifest_entry in manifest["trees"]:
        tree_id = str(manifest_entry["id"])
        tree = trees[tree_id]
        nodes: list[ObservedResearchNode] = []
        for raw_node in tree["nodes"]:
            effects = raw_node.get("effects", [])
            if len(effects) > 1:
                raise ValueError(
                    f"{tree_id}.{raw_node['id']}: the compatibility observation "
                    "model supports at most one effect"
                )
            effect = effects[0] if effects else None
            levels: dict[int, ObservedResearchLevel] = {}
            for raw_level in raw_node["levels"]:
                costs = raw_level.get("costs")
                level_number = int(raw_level["level"])
                levels[level_number] = ObservedResearchLevel(
                    level=level_number,
                    academy_level=raw_level.get("academy_level"),
                    base_time_seconds=raw_level.get("base_time_seconds"),
                    technolabe_count=raw_level.get("technolabe_count"),
                    costs=dict(costs or {}),
                    power=raw_level.get("power"),
                    requirements=tuple(
                        ObservedResearchRequirement(
                            research_id=str(item["research_id"]),
                            level=int(item["level"]),
                        )
                        for item in raw_level.get("prerequisites", [])
                    ),
                    building_requirements=dict(raw_level.get("buildings") or {}),
                    costs_verified=bool(
                        raw_level.get("costs_complete", costs is not None)
                    ),
                    verification_status=_verification_status(raw_level, tree),
                )
            node_id = str(raw_node["id"])
            nodes.append(
                ObservedResearchNode(
                    id=node_id,
                    names={
                        locale: document["research"][node_id]
                        for locale, document in locales.items()
                        if node_id in document.get("research", {})
                    },
                    max_level=int(raw_node["max_level"]),
                    row=int(raw_node["layout"]["row"]),
                    column=int(raw_node["layout"]["column"]),
                    effect_label=(
                        str(locales["en-US"]["metrics"].get(effect["metric_id"], ""))
                        if effect
                        else ""
                    ),
                    effect_values=(
                        {
                            int(item["level"]): str(
                                item.get("display_fallback", item["value"])
                            )
                            for item in effect["values"]
                        }
                        if effect
                        else {}
                    ),
                    levels=levels,
                )
            )
        source_url, license_name, license_url = _source_metadata(
            tree,
            sources_by_id,
        )
        tree_verification = tree["default_verification"]
        legacy_compatibility = tree.get("legacy_compatibility")
        if not isinstance(legacy_compatibility, Mapping):
            legacy_compatibility = {}
        observations.append(
            ResearchTreeObservation(
                observation_id=f"catalog-{tree_id}",
                category_id=tree_id,
                titles={
                    locale: document["trees"][tree_id]
                    for locale, document in locales.items()
                    if tree_id in document.get("trees", {})
                },
                locale="en-US",
                source_type=str(
                    legacy_compatibility.get("source_type") or "research_dataset"
                ),
                verification_status=str(
                    legacy_compatibility.get("verification_status")
                    or tree_verification.get("status")
                    or "provisional"
                ),
                captured_on=str(manifest["checked_on"]),
                game_version=str(manifest["game_version"]),
                scope=str(
                    legacy_compatibility.get("scope") or tree["coverage"]
                ),
                notes=str(
                    legacy_compatibility.get("notes")
                    or tree_verification.get("notes")
                    or ""
                ),
                nodes=tuple(nodes),
                edges=tuple(
                    ObservedResearchEdge(
                        prerequisite_id=str(item["prerequisite_id"]),
                        research_id=str(item["research_id"]),
                    )
                    for item in tree["source_edges"]
                ),
                source_url=source_url,
                license_name=license_name,
                license_url=license_url,
                connection_groups=tuple(
                    ObservedResearchConnectionGroup(
                        prerequisite_ids=tuple(item["from_ids"]),
                        research_ids=tuple(item["to_ids"]),
                    )
                    for item in tree["display_connections"]
                ),
            )
        )
    observation_ids = [item.observation_id for item in observations]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("Research dataset contains duplicate observation IDs")
    return tuple(observations)
