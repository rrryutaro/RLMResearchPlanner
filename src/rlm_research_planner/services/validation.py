from __future__ import annotations

from dataclasses import dataclass

from rlm_research_planner.domain.models import MasterData, RESOURCE_KEYS


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"


class MasterDataValidator:
    def validate(self, master: MasterData) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        category_ids = [item.id for item in master.categories]
        research_ids = [item.id for item in master.research]
        self._duplicates(category_ids, "category", issues)
        self._duplicates(research_ids, "research", issues)
        category_set = set(category_ids)
        research_set = set(research_ids)

        for research in master.research:
            if research.category_id not in category_set:
                issues.append(
                    ValidationIssue(
                        "unknown_category",
                        f"{research.id} uses unknown category {research.category_id}",
                    )
                )
            levels = master.levels_by_research(research.id)
            actual = [item.level for item in levels]
            expected = list(range(1, research.max_level + 1))
            if actual != expected:
                issues.append(
                    ValidationIssue(
                        "level_gap",
                        f"{research.id} levels are {actual}; expected {expected}",
                    )
                )

        seen_levels: set[tuple[str, int]] = set()
        for level in master.levels:
            key = (level.research_id, level.level)
            if key in seen_levels:
                issues.append(ValidationIssue("duplicate_level", f"Duplicate level {key}"))
            seen_levels.add(key)
            if level.research_id not in research_set:
                issues.append(
                    ValidationIssue("unknown_research", f"Unknown research {level.research_id}")
                )
            if level.base_time_seconds < 0 or level.power < 0:
                issues.append(ValidationIssue("negative_value", f"Negative value in {key}"))
            if any(int(level.resources.get(resource, 0)) < 0 for resource in RESOURCE_KEYS):
                issues.append(ValidationIssue("negative_resource", f"Negative resource in {key}"))
            if not level.source:
                issues.append(ValidationIssue("missing_source", f"Missing source in {key}"))
            if not level.checked_on:
                issues.append(ValidationIssue("missing_checked_on", f"Missing date in {key}"))

        graph: dict[str, set[str]] = {research_id: set() for research_id in research_set}
        for prerequisite in master.prerequisites:
            if prerequisite.research_id not in research_set:
                issues.append(
                    ValidationIssue(
                        "unknown_target", f"Unknown target {prerequisite.research_id}"
                    )
                )
            prerequisite_id = prerequisite.prerequisite_research_id
            if prerequisite_id:
                if prerequisite_id not in research_set:
                    issues.append(
                        ValidationIssue(
                            "unknown_prerequisite", f"Unknown prerequisite {prerequisite_id}"
                        )
                    )
                elif prerequisite.research_id in graph:
                    graph[prerequisite.research_id].add(prerequisite_id)
        issues.extend(self._cycles(graph))
        return issues
    @staticmethod
    def _duplicates(values: list[str], kind: str, issues: list[ValidationIssue]) -> None:
        seen: set[str] = set()
        for value in values:
            if value in seen:
                issues.append(ValidationIssue(f"duplicate_{kind}", f"Duplicate {kind} {value}"))
            seen.add(value)

    @staticmethod
    def _cycles(graph: dict[str, set[str]]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(node: str, path: list[str]) -> None:
            if node in visiting:
                start = path.index(node) if node in path else 0
                cycle = path[start:] + [node]
                issues.append(
                    ValidationIssue("cycle", " -> ".join(cycle))
                )
                return
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph.get(node, set()):
                visit(dependency, path + [node])
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node, [])
        return issues
