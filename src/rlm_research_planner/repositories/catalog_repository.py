from __future__ import annotations

import json
import re
from pathlib import Path

from rlm_research_planner.domain.observations import (
    ObservedResearchConnectionGroup,
    ObservedResearchEdge,
    ObservedResearchLevel,
    ObservedResearchNode,
    ObservedResearchRequirement,
    ResearchTreeObservation,
)


class JsonResearchCatalogRepository:
    """Load the name/layout catalog separately from calculation master data."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load_all(self) -> tuple[ResearchTreeObservation, ...]:
        if not self.path.is_file():
            return ()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            sources = raw.get("sources")
            if isinstance(sources, list) and sources:
                source = sources[0]
            else:
                source = raw["source"]
            research_ids = self._catalog_research_ids(raw["categories"])
            categories = tuple(
                self._load_category(item, raw, source, research_ids)
                for item in raw["categories"]
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid research catalog {self.path.name}: {exc}") from exc
        ids = [category.observation_id for category in categories]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.path.name}: duplicate category id")
        return categories

    def _load_category(
        self,
        raw: dict[str, object],
        catalog: dict[str, object],
        source: dict[str, object],
        research_ids: dict[str, str],
    ) -> ResearchTreeObservation:
        category_id = str(raw["id"])
        id_overrides = self._string_mapping(raw.get("id_overrides", {}))
        max_levels = raw.get("max_levels", {})
        if not isinstance(max_levels, dict):
            raise ValueError(f"{category_id}: max_levels must be an object")
        localized_names = raw.get("localized_names", {})
        if not isinstance(localized_names, dict):
            raise ValueError(f"{category_id}: localized_names must be an object")
        effects = raw.get("effects", {})
        if not isinstance(effects, dict):
            raise ValueError(f"{category_id}: effects must be an object")

        nodes: list[ObservedResearchNode] = []
        name_to_id: dict[str, str] = {}
        rows = raw.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError(f"{category_id}: rows must be an array")
        for row_index, row in enumerate(rows):
            if not isinstance(row, list):
                raise ValueError(f"{category_id}: every row must be an array")
            for column_index, value in enumerate(row):
                if value is None:
                    continue
                name = str(value).strip()
                if not name or name in name_to_id:
                    raise ValueError(f"{category_id}: empty or duplicate research name")
                research_id = id_overrides.get(name, self._research_id(category_id, name))
                names = {"en-US": name}
                translations = localized_names.get(name, {})
                if isinstance(translations, dict):
                    names.update(
                        {
                            str(locale): str(text).strip()
                            for locale, text in translations.items()
                            if str(text).strip()
                        }
                    )
                maximum = max_levels.get(name)
                raw_effect = effects.get(name, {})
                if not isinstance(raw_effect, dict):
                    raw_effect = {}
                raw_effect_levels = raw_effect.get("levels", {})
                if not isinstance(raw_effect_levels, dict):
                    raw_effect_levels = {}
                raw_level_data = raw.get("level_data", {})
                if not isinstance(raw_level_data, dict):
                    raise ValueError(f"{category_id}: level_data must be an object")
                raw_research_levels = raw_level_data.get(name, {})
                if not isinstance(raw_research_levels, dict):
                    raise ValueError(
                        f"{category_id}: level_data for {name} must be an object"
                    )
                level_data: dict[int, ObservedResearchLevel] = {}
                for level_text, raw_level in raw_research_levels.items():
                    if not str(level_text).isdigit() or not isinstance(raw_level, dict):
                        raise ValueError(f"{category_id}: invalid level data for {name}")
                    level_number = int(level_text)
                    raw_requirements = raw_level.get("requirements", [])
                    if not isinstance(raw_requirements, list):
                        raise ValueError(
                            f"{category_id}: requirements for {name} must be an array"
                        )
                    requirements: list[ObservedResearchRequirement] = []
                    for requirement in raw_requirements:
                        if not isinstance(requirement, dict):
                            raise ValueError(
                                f"{category_id}: invalid requirement for {name}"
                            )
                        prerequisite_name = str(requirement.get("research", ""))
                        prerequisite_id = research_ids.get(prerequisite_name)
                        if not prerequisite_id:
                            raise ValueError(
                                f"{category_id}: unknown prerequisite {prerequisite_name}"
                            )
                        requirements.append(
                            ObservedResearchRequirement(
                                research_id=prerequisite_id,
                                level=int(requirement["level"]),
                            )
                        )
                    costs = raw_level.get("costs", {})
                    buildings = raw_level.get("buildings", {})
                    if not isinstance(costs, dict) or not isinstance(buildings, dict):
                        raise ValueError(f"{category_id}: invalid costs/buildings for {name}")
                    academy = raw_level.get("academy_level")
                    base_time = raw_level.get("base_time_seconds")
                    power = raw_level.get("power")
                    level_data[level_number] = ObservedResearchLevel(
                        level=level_number,
                        academy_level=int(academy) if academy is not None else None,
                        base_time_seconds=(
                            int(base_time) if base_time is not None else None
                        ),
                        costs={str(key): int(value) for key, value in costs.items()},
                        power=int(power) if power is not None else None,
                        requirements=tuple(requirements),
                        building_requirements={
                            str(key): int(value) for key, value in buildings.items()
                        },
                        costs_verified=bool(raw_level.get("costs_verified", False)),
                        verification_status=str(
                            raw_level.get("verification_status", "unverified")
                        ),
                    )
                nodes.append(
                    ObservedResearchNode(
                        id=research_id,
                        names=names,
                        max_level=int(maximum) if maximum is not None else None,
                        row=row_index,
                        column=column_index,
                        effect_label=str(raw_effect.get("label", "")).strip(),
                        effect_values={
                            int(level): str(effect).strip()
                            for level, effect in raw_effect_levels.items()
                            if str(level).isdigit() and str(effect).strip()
                        },
                        levels=level_data,
                    )
                )
                name_to_id[name] = research_id

        edges: list[ObservedResearchEdge] = []
        raw_edges = raw.get("edges", [])
        if not isinstance(raw_edges, list):
            raise ValueError(f"{category_id}: edges must be an array")
        for pair in raw_edges:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"{category_id}: edge must contain two names")
            prerequisite, research = (str(item) for item in pair)
            if prerequisite not in name_to_id or research not in name_to_id:
                raise ValueError(f"{category_id}: edge references an unknown name")
            edges.append(
                ObservedResearchEdge(name_to_id[prerequisite], name_to_id[research])
            )

        connection_groups: list[ObservedResearchConnectionGroup] = []
        raw_groups = raw.get("connection_groups", [])
        if not isinstance(raw_groups, list):
            raise ValueError(f"{category_id}: connection_groups must be an array")
        for group in raw_groups:
            if not isinstance(group, dict):
                raise ValueError(f"{category_id}: connection group must be an object")
            prerequisites = group.get("prerequisites", [])
            research = group.get("research", [])
            if (
                not isinstance(prerequisites, list)
                or not isinstance(research, list)
                or not prerequisites
                or not research
            ):
                raise ValueError(
                    f"{category_id}: connection group needs prerequisites and research"
                )
            prerequisite_names = tuple(str(item) for item in prerequisites)
            research_names = tuple(str(item) for item in research)
            if any(name not in name_to_id for name in (*prerequisite_names, *research_names)):
                raise ValueError(
                    f"{category_id}: connection group references an unknown name"
                )
            connection_groups.append(
                ObservedResearchConnectionGroup(
                    prerequisite_ids=tuple(
                        name_to_id[name] for name in prerequisite_names
                    ),
                    research_ids=tuple(name_to_id[name] for name in research_names),
                )
            )
        if not connection_groups:
            connection_groups.extend(
                self._level_one_connection_groups(nodes, edges)
            )

        titles = raw.get("titles")
        if not isinstance(titles, dict) or not titles:
            raise ValueError(f"{category_id}: titles are required")
        status = str(raw.get("verification_status", "names_verified_layout_approximate"))
        return ResearchTreeObservation(
            observation_id=f"catalog-{category_id}",
            category_id=category_id,
            titles={str(key): str(value) for key, value in titles.items()},
            locale="en-US",
            source_type="community_catalog",
            verification_status=status,
            captured_on=str(catalog.get("checked_on", "")),
            game_version=str(catalog.get("game_version", "unknown")),
            scope=str(raw.get("scope", "all_names_layout_only")),
            notes=str(raw.get("notes", catalog.get("notes", ""))),
            nodes=tuple(nodes),
            edges=tuple(edges),
            source_url=str(raw.get("source_url", source.get("url", ""))),
            license_name=str(raw.get("license_name", source.get("license", ""))),
            license_url=str(raw.get("license_url", source.get("license_url", ""))),
            connection_groups=tuple(connection_groups),
        )

    @staticmethod
    def _level_one_connection_groups(
        nodes: list[ObservedResearchNode],
        edges: list[ObservedResearchEdge],
    ) -> tuple[ObservedResearchConnectionGroup, ...]:
        """Build clean connections that follow the visible research tree.

        The catalog ``edges`` contain every prerequisite encountered at every
        level and level-one data can also contain transitive or cross-category
        requirements.  The game tree only draws the nearest visible tier.  Use
        both sources, discard external and later-row references, then retain
        the nearest row for each child.  A level-one prerequisite on an earlier
        row is also retained when its source column is unobstructed, matching
        the longer vertical branches used by the game.  Same-row requirements
        are kept so center cards can connect horizontally to their side cards.
        """

        by_id = {node.id: node for node in nodes}
        incoming: dict[str, set[str]] = {}
        level_one_incoming: dict[str, set[str]] = {}
        for edge in edges:
            if edge.prerequisite_id in by_id and edge.research_id in by_id:
                incoming.setdefault(edge.research_id, set()).add(
                    edge.prerequisite_id
                )
        for node in nodes:
            level_one = node.level_data(1)
            if level_one is None:
                continue
            direct_prerequisites = {
                requirement.research_id
                for requirement in level_one.requirements
                if requirement.research_id in by_id
                and by_id[requirement.research_id].row <= node.row
            }
            if direct_prerequisites:
                level_one_incoming[node.id] = direct_prerequisites
                incoming.setdefault(node.id, set()).update(direct_prerequisites)

        occupied_positions = {(node.row, node.column) for node in nodes}
        grouped: dict[tuple[int, int, tuple[str, ...]], list[str]] = {}
        for node in sorted(nodes, key=lambda item: (item.row, item.column)):
            candidates = [
                by_id[research_id]
                for research_id in incoming.get(node.id, set())
                if research_id != node.id
                and by_id[research_id].row <= node.row
            ]
            if not candidates:
                continue
            nearest_row = max(item.row for item in candidates)
            direct_on_nearest_row = {
                research_id
                for research_id in level_one_incoming.get(node.id, set())
                if by_id[research_id].row == nearest_row
            }
            selected_ids = direct_on_nearest_row or {
                candidate.id
                for candidate in candidates
                if candidate.row == nearest_row
            }
            for research_id in level_one_incoming.get(node.id, set()):
                prerequisite = by_id[research_id]
                if (
                    prerequisite.row < nearest_row
                    and all(
                        (row, prerequisite.column) not in occupied_positions
                        for row in range(
                            prerequisite.row + 1, node.row
                        )
                    )
                ):
                    selected_ids.add(prerequisite.id)
            selected_by_row: dict[int, list[ObservedResearchNode]] = {}
            for research_id in selected_ids:
                prerequisite = by_id[research_id]
                selected_by_row.setdefault(prerequisite.row, []).append(
                    prerequisite
                )
            for prerequisite_row, selected in selected_by_row.items():
                prerequisite_ids = tuple(
                    item.id
                    for item in sorted(
                        selected,
                        key=lambda item: (item.column, item.id),
                    )
                )
                grouped.setdefault(
                    (prerequisite_row, node.row, prerequisite_ids), []
                ).append(node.id)
        selected_pairs = {
            (prerequisite_id, research_id)
            for (
                _prerequisite_row,
                _research_row,
                prerequisite_ids,
            ), research_ids in grouped.items()
            for prerequisite_id in prerequisite_ids
            for research_id in research_ids
        }
        branches_by_rows: dict[
            tuple[int, int], list[tuple[set[str], set[str]]]
        ] = {}
        for (
            prerequisite_row,
            research_row,
            prerequisite_ids,
        ), research_ids in grouped.items():
            branches_by_rows.setdefault(
                (prerequisite_row, research_row), []
            ).append((set(prerequisite_ids), set(research_ids)))

        # A shared prerequisite must produce one visual bus for a row pair.
        # Keeping each child set as a separate group draws the same vertical
        # stem and horizontal bus repeatedly, which looks like unrelated or
        # disconnected lines even though the underlying dependency is valid.
        merged_groups: list[ObservedResearchConnectionGroup] = []
        for row_pair in sorted(branches_by_rows):
            remaining = list(branches_by_rows[row_pair])
            while remaining:
                prerequisite_set, research_set = remaining.pop(0)
                merged = True
                while merged:
                    merged = False
                    for index in range(len(remaining) - 1, -1, -1):
                        other_prerequisites, other_research = remaining[index]
                        if not (
                            prerequisite_set & other_prerequisites
                            or research_set & other_research
                        ):
                            continue
                        combined_prerequisites = (
                            prerequisite_set | other_prerequisites
                        )
                        combined_research = research_set | other_research
                        if any(
                            (prerequisite_id, research_id) not in selected_pairs
                            for prerequisite_id in combined_prerequisites
                            for research_id in combined_research
                        ):
                            continue
                        prerequisite_set = combined_prerequisites
                        research_set = combined_research
                        remaining.pop(index)
                        merged = True
                merged_groups.append(
                    ObservedResearchConnectionGroup(
                        prerequisite_ids=tuple(
                            sorted(
                                prerequisite_set,
                                key=lambda research_id: (
                                    by_id[research_id].column,
                                    research_id,
                                ),
                            )
                        ),
                        research_ids=tuple(
                            sorted(
                                research_set,
                                key=lambda research_id: (
                                    by_id[research_id].column,
                                    research_id,
                                ),
                            )
                        ),
                    )
                )
        return tuple(merged_groups)

    @staticmethod
    def _string_mapping(value: object) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError("id_overrides must be an object")
        return {str(key): str(mapped) for key, mapped in value.items()}

    def _catalog_research_ids(self, categories: object) -> dict[str, str]:
        if not isinstance(categories, list):
            raise ValueError("categories must be an array")
        result: dict[str, str] = {}
        for category in categories:
            if not isinstance(category, dict):
                raise ValueError("category must be an object")
            category_id = str(category["id"])
            overrides = self._string_mapping(category.get("id_overrides", {}))
            rows = category.get("rows", [])
            if not isinstance(rows, list):
                raise ValueError(f"{category_id}: rows must be an array")
            for row in rows:
                if not isinstance(row, list):
                    raise ValueError(f"{category_id}: every row must be an array")
                for value in row:
                    if value is None:
                        continue
                    name = str(value).strip()
                    research_id = overrides.get(
                        name, self._research_id(category_id, name)
                    )
                    if name in result and result[name] != research_id:
                        raise ValueError(f"duplicate research name across categories: {name}")
                    result[name] = research_id
        return result

    @staticmethod
    def _research_id(category_id: str, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
        if not slug:
            raise ValueError(f"Unable to create id for {name!r}")
        return f"{category_id}_{slug}"
