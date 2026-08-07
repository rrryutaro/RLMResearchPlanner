from __future__ import annotations

import json
from pathlib import Path

from rlm_research_planner.domain.observations import (
    ObservedResearchEdge,
    ObservedResearchNode,
    ResearchTreeObservation,
)


class JsonObservationRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def load_all(self) -> tuple[ResearchTreeObservation, ...]:
        observations: list[ResearchTreeObservation] = []
        seen_ids: set[str] = set()
        if not self.directory.is_dir():
            return ()
        for path in sorted(self.directory.glob("*.json")):
            observation = self._load(path)
            if observation.observation_id in seen_ids:
                raise ValueError(
                    f"Duplicate observation id: {observation.observation_id}"
                )
            seen_ids.add(observation.observation_id)
            observations.append(observation)
        return tuple(observations)

    def _load(self, path: Path) -> ResearchTreeObservation:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            locale = str(raw["locale"])
            nodes = tuple(
                ObservedResearchNode(
                    id=str(item["id"]),
                    names=self._localized_values(item, "names", "name", locale),
                    max_level=(
                        int(item["max_level"])
                        if item.get("max_level") is not None
                        else None
                    ),
                    row=int(item["row"]),
                    column=int(item["column"]),
                )
                for item in raw["nodes"]
            )
            edges = tuple(
                ObservedResearchEdge(
                    prerequisite_id=str(item["prerequisite_id"]),
                    research_id=str(item["research_id"]),
                )
                for item in raw["edges"]
            )
            observation = ResearchTreeObservation(
                observation_id=str(raw["observation_id"]),
                category_id=str(raw["category_id"]),
                titles=self._localized_values(raw, "titles", "title", locale),
                locale=locale,
                source_type=str(raw["source_type"]),
                verification_status=str(raw["verification_status"]),
                captured_on=str(raw.get("captured_on", "")),
                game_version=str(raw.get("game_version", "unknown")),
                scope=str(raw["scope"]),
                notes=str(raw.get("notes", "")),
                nodes=nodes,
                edges=edges,
                source_url=str(raw.get("source_url", "")),
                license_name=str(raw.get("license_name", "")),
                license_url=str(raw.get("license_url", "")),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid observation file {path.name}: {exc}") from exc
        self._validate(observation, path.name)
        return observation

    @staticmethod
    def _localized_values(
        raw: dict[str, object], mapping_key: str, value_key: str, locale: str
    ) -> dict[str, str]:
        mapping = raw.get(mapping_key)
        if isinstance(mapping, dict):
            values = {
                str(key): str(value).strip()
                for key, value in mapping.items()
                if str(value).strip()
            }
            if values:
                return values
        value = str(raw.get(value_key, "")).strip()
        return {locale: value} if value else {}

    @staticmethod
    def _validate(observation: ResearchTreeObservation, filename: str) -> None:
        if not observation.observation_id:
            raise ValueError(f"{filename}: observation_id is required")
        if not observation.titles:
            raise ValueError(f"{filename}: at least one title is required")
        node_ids = [node.id for node in observation.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError(f"{filename}: duplicate research node id")
        node_set = set(node_ids)
        for node in observation.nodes:
            if not node.id or not node.names:
                raise ValueError(f"{filename}: node id and name are required")
            if (
                (node.max_level is not None and node.max_level < 1)
                or node.row < 0
                or node.column < 0
            ):
                raise ValueError(f"{filename}: invalid node values for {node.id}")
        graph: dict[str, set[str]] = {node_id: set() for node_id in node_set}
        for edge in observation.edges:
            if edge.prerequisite_id not in node_set or edge.research_id not in node_set:
                raise ValueError(f"{filename}: edge references an unknown node")
            if edge.prerequisite_id == edge.research_id:
                raise ValueError(f"{filename}: self-referencing edge")
            graph[edge.research_id].add(edge.prerequisite_id)

        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError(f"{filename}: cyclic observation tree at {node_id}")
            if node_id in visited:
                return
            visiting.add(node_id)
            for prerequisite_id in graph[node_id]:
                visit(prerequisite_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in graph:
            visit(node_id)
