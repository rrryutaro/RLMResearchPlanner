from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover - exercised by the actionable error below
    Draft202012Validator = None  # type: ignore[assignment,misc]
    Registry = None  # type: ignore[assignment,misc]
    Resource = None  # type: ignore[assignment,misc]


DATASET_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = DATASET_PACKAGE_ROOT / "schemas"
ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
VERIFICATION_STATUSES = {
    "verified",
    "cross_checked",
    "provisional",
    "disputed",
}
DOCUMENT_SCHEMAS = {
    "manifest": "manifest.schema.json",
    "sources": "sources.schema.json",
    "evidence": "evidence.schema.json",
    "aliases": "aliases.schema.json",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative_file(root: Path, raw_path: object) -> Path:
    value = str(raw_path or "")
    if not value or "\\" in value:
        raise ValueError(f"invalid relative path: {value!r}")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes dataset root: {value}")
    if not path.is_file():
        raise ValueError(f"dataset file does not exist: {value}")
    return path


def load_dataset(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest = _read_json(root / "manifest.json")
    sources = _read_json(_relative_file(root, manifest.get("sources_path")))
    evidence = _read_json(_relative_file(root, manifest.get("evidence_path")))
    aliases = _read_json(_relative_file(root, manifest.get("aliases_path")))
    trees: dict[str, Any] = {}
    for item in manifest.get("trees", []):
        tree_id = str(item.get("id", ""))
        if tree_id in trees:
            raise ValueError(f"duplicate manifest tree id: {tree_id}")
        trees[tree_id] = _read_json(_relative_file(root, item.get("path")))
    locales: dict[str, Any] = {}
    required_locales: set[str] = set()
    for item in manifest.get("locales", []):
        locale = str(item.get("locale", ""))
        if locale in locales:
            raise ValueError(f"duplicate manifest locale: {locale}")
        locales[locale] = _read_json(_relative_file(root, item.get("path")))
        if item.get("required") is True:
            required_locales.add(locale)
    return {
        "manifest": manifest,
        "sources": sources,
        "evidence": evidence,
        "aliases": aliases,
        "trees": trees,
        "locales": locales,
        "required_locales": required_locales,
    }


def validate_schema_documents(schema_root: Path = SCHEMA_ROOT) -> list[str]:
    errors: list[str] = []
    documents: dict[str, Any] = {}
    ids: dict[str, str] = {}
    for path in sorted(Path(schema_root).glob("*.schema.json")):
        try:
            document = _read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"schema {path.name}: {exc}")
            continue
        documents[path.name] = document
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"schema {path.name}: unsupported meta-schema")
        schema_id = str(document.get("$id", ""))
        if not schema_id:
            errors.append(f"schema {path.name}: missing $id")
        elif schema_id in ids:
            errors.append(
                f"schema {path.name}: duplicate $id also used by {ids[schema_id]}"
            )
        else:
            ids[schema_id] = path.name
    for name, document in documents.items():
        for reference in _references(document):
            if reference.startswith(("#", "http://", "https://")):
                continue
            target = reference.split("#", 1)[0]
            if target and target not in documents:
                errors.append(f"schema {name}: unresolved $ref {reference}")
    if not documents:
        errors.append("no schema documents found")
    if Draft202012Validator is None:
        errors.append(
            "jsonschema is required for Draft 2020-12 validation; "
            "install the project's dev dependencies"
        )
    else:
        for name, document in documents.items():
            try:
                Draft202012Validator.check_schema(document)
            except Exception as exc:  # jsonschema exposes several schema errors
                errors.append(f"schema {name}: {exc}")
    return errors


def _schema_error_path(prefix: str, path: Iterable[object]) -> str:
    result = prefix
    for item in path:
        if isinstance(item, int):
            result += f"[{item}]"
        else:
            result += f".{item}"
    return result


def validate_schema_instances(
    documents: dict[str, Any],
    schema_root: Path = SCHEMA_ROOT,
) -> list[str]:
    if Draft202012Validator is None or Registry is None or Resource is None:
        return [
            "jsonschema is required for dataset validation; "
            "install the project's dev dependencies"
        ]
    schemas = {
        path.name: _read_json(path)
        for path in sorted(Path(schema_root).glob("*.schema.json"))
    }
    registry = Registry().with_resources(
        (
            str(schema["$id"]),
            Resource.from_contents(schema),
        )
        for schema in schemas.values()
    )
    targets: list[tuple[str, str, Any]] = [
        (name, schema_name, documents.get(name))
        for name, schema_name in DOCUMENT_SCHEMAS.items()
    ]
    targets.extend(
        (f"tree {tree_id}", "research-tree.schema.json", tree)
        for tree_id, tree in documents.get("trees", {}).items()
    )
    targets.extend(
        (f"locale {locale}", "locale.schema.json", document)
        for locale, document in documents.get("locales", {}).items()
    )
    errors: list[str] = []
    for name, schema_name, instance in targets:
        schema = schemas.get(schema_name)
        if schema is None:
            errors.append(f"{name}: missing schema {schema_name}")
            continue
        validator = Draft202012Validator(schema, registry=registry)
        for error in sorted(
            validator.iter_errors(instance),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        ):
            path = _schema_error_path(name, error.absolute_path)
            errors.append(f"{path}: {error.message}")
    return errors


def _references(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str):
                yield item
            else:
                yield from _references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _references(item)


def _verification_errors(
    value: object,
    path: str,
    source_ids: set[str],
    evidence_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return [f"{path}: verification must be an object"]
    status = str(value.get("status", ""))
    sources = [str(item) for item in value.get("source_ids", [])]
    evidence = [str(item) for item in value.get("evidence_ids", [])]
    if status not in VERIFICATION_STATUSES:
        errors.append(f"{path}: invalid verification status {status!r}")
    for source_id in sources:
        if source_id not in source_ids:
            errors.append(f"{path}: unknown source id {source_id}")
    for evidence_id in evidence:
        if evidence_id not in evidence_ids:
            errors.append(f"{path}: unknown evidence id {evidence_id}")
    if status == "verified" and not evidence:
        errors.append(f"{path}: verified facts require direct evidence")
    if status == "cross_checked" and len(set(sources + evidence)) < 2:
        errors.append(f"{path}: cross_checked facts require two references")
    if status == "disputed" and not str(value.get("notes", "")).strip():
        errors.append(f"{path}: disputed facts require notes")
    return errors


def _all_verifications(value: dict[str, Any]) -> Iterable[tuple[str, object]]:
    if "default_verification" in value:
        yield "default_verification", value["default_verification"]
    if "verification" in value:
        yield "verification", value["verification"]
    overrides = value.get("verification_overrides", {})
    if isinstance(overrides, dict):
        for name, verification in overrides.items():
            yield f"verification_overrides.{name}", verification


def validate_documents(documents: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    manifest = documents.get("manifest", {})
    trees = documents.get("trees", {})
    locales = documents.get("locales", {})
    required_locales = set(documents.get("required_locales", set()))
    sources_document = documents.get("sources", {})
    evidence_document = documents.get("evidence", {})
    aliases_document = documents.get("aliases", {})

    source_records = sources_document.get("sources", [])
    source_ids = [str(item.get("id", "")) for item in source_records]
    evidence_records = evidence_document.get("evidence", [])
    evidence_ids = [str(item.get("id", "")) for item in evidence_records]
    if len(source_ids) != len(set(source_ids)):
        errors.append("sources: duplicate source id")
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("evidence: duplicate evidence id")
    known_sources = set(source_ids)
    known_evidence = set(evidence_ids)
    for item in source_records:
        if not ID_PATTERN.fullmatch(str(item.get("id", ""))):
            errors.append(f"sources: invalid source id {item.get('id')!r}")
        license_value = item.get("license")
        if not isinstance(license_value, dict) or not str(
            license_value.get("attribution", "")
        ).strip():
            errors.append(f"source {item.get('id')}: license attribution is required")
    for item in evidence_records:
        evidence_id = str(item.get("id", ""))
        if not ID_PATTERN.fullmatch(evidence_id):
            errors.append(f"evidence: invalid evidence id {evidence_id!r}")
        for source_id in item.get("source_ids", []):
            if source_id not in known_sources:
                errors.append(f"evidence {evidence_id}: unknown source id {source_id}")

    manifest_tree_ids = [str(item.get("id", "")) for item in manifest.get("trees", [])]
    if len(manifest_tree_ids) != len(set(manifest_tree_ids)):
        errors.append("manifest: duplicate tree id")
    if set(manifest_tree_ids) != set(trees):
        errors.append("manifest: loaded tree IDs do not match declared tree IDs")

    nodes: dict[str, dict[str, Any]] = {}
    node_tree: dict[str, str] = {}
    metric_ids: set[str] = set()
    graph: dict[tuple[str, int], set[tuple[str, int]]] = defaultdict(set)
    for tree_id, tree in trees.items():
        if tree.get("tree_id") != tree_id:
            errors.append(f"tree {tree_id}: document tree_id does not match manifest")
        errors.extend(
            _verification_errors(
                tree.get("default_verification"),
                f"tree {tree_id}.default_verification",
                known_sources,
                known_evidence,
            )
        )
        for name, verification in _all_verifications(tree):
            if name == "default_verification":
                continue
            errors.extend(
                _verification_errors(
                    verification,
                    f"tree {tree_id}.{name}",
                    known_sources,
                    known_evidence,
                )
            )
        positions: set[tuple[int, int]] = set()
        tree_node_ids: set[str] = set()
        for node in tree.get("nodes", []):
            research_id = str(node.get("id", ""))
            if not ID_PATTERN.fullmatch(research_id):
                errors.append(f"tree {tree_id}: invalid research id {research_id!r}")
            if research_id in nodes:
                errors.append(f"tree {tree_id}: duplicate research id {research_id}")
                continue
            nodes[research_id] = node
            node_tree[research_id] = tree_id
            tree_node_ids.add(research_id)
            layout = node.get("layout", {})
            position = (layout.get("row"), layout.get("column"))
            if not all(isinstance(value, int) and value >= 0 for value in position):
                errors.append(f"research {research_id}: invalid layout position")
            elif position in positions:
                errors.append(f"tree {tree_id}: duplicate layout position {position}")
            positions.add(position)
            maximum = node.get("max_level")
            if not isinstance(maximum, int) or maximum < 1:
                errors.append(f"research {research_id}: invalid max_level")
                maximum = 0
            levels = node.get("levels", [])
            level_numbers = [item.get("level") for item in levels]
            if len(level_numbers) != len(set(level_numbers)):
                errors.append(f"research {research_id}: duplicate level record")
            if tree.get("coverage") == "complete" and set(level_numbers) != set(
                range(1, maximum + 1)
            ):
                errors.append(f"research {research_id}: complete tree has level gaps")
            for level_number in range(1, maximum + 1):
                graph[(research_id, level_number)]
                if level_number > 1:
                    graph[(research_id, level_number)].add(
                        (research_id, level_number - 1)
                    )
            for level in levels:
                level_number = level.get("level")
                if not isinstance(level_number, int) or not 1 <= level_number <= maximum:
                    errors.append(f"research {research_id}: invalid level {level_number}")
                    continue
                for field in ("base_time_seconds", "technolabe_count", "power"):
                    value = level.get(field)
                    if field in level and value is not None and (
                        not isinstance(value, int) or value < 0
                    ):
                        errors.append(
                            f"research {research_id} level {level_number}: negative or invalid {field}"
                        )
                costs = level.get("costs")
                if isinstance(costs, dict):
                    for resource_id, amount in costs.items():
                        if not isinstance(amount, int) or amount < 0:
                            errors.append(
                                f"research {research_id} level {level_number}: invalid cost {resource_id}"
                            )
                for name, verification in _all_verifications(level):
                    errors.extend(
                        _verification_errors(
                            verification,
                            f"research {research_id} level {level_number}.{name}",
                            known_sources,
                            known_evidence,
                        )
                    )
            for effect in node.get("effects", []):
                metric_id = str(effect.get("metric_id", ""))
                if not ID_PATTERN.fullmatch(metric_id):
                    errors.append(f"research {research_id}: invalid metric id {metric_id!r}")
                metric_ids.add(metric_id)
                values = [item.get("level") for item in effect.get("values", [])]
                if len(values) != len(set(values)) or any(
                    not isinstance(level, int) or not 1 <= level <= maximum
                    for level in values
                ):
                    errors.append(f"research {research_id}: invalid effect levels")
                if effect.get("parsed") is False:
                    if effect.get("unit") != "text":
                        errors.append(
                            f"research {research_id}: unparsed effect must use text unit"
                        )
                    if any(
                        not str(item.get("display_fallback") or "").strip()
                        for item in effect.get("values", [])
                    ):
                        errors.append(
                            f"research {research_id}: unparsed effect needs display fallback"
                        )
            lifecycle = node.get("lifecycle", {"state": "active"})
            state = lifecycle.get("state") if isinstance(lifecycle, dict) else ""
            if state not in {"active", "deprecated"}:
                errors.append(f"research {research_id}: invalid lifecycle state")
            if state == "active" and lifecycle.get("superseded_by"):
                errors.append(f"research {research_id}: active record cannot be superseded")

        tree_level_count = sum(
            len(node.get("levels", [])) for node in tree.get("nodes", [])
        )
        if tree.get("coverage") == "structure_only" and tree_level_count:
            errors.append(f"tree {tree_id}: structure_only tree contains level data")

        seen_source_edges: set[tuple[str, str]] = set()
        for index, edge in enumerate(tree.get("source_edges", [])):
            prerequisite_id = str(edge.get("prerequisite_id", ""))
            research_id = str(edge.get("research_id", ""))
            pair = (prerequisite_id, research_id)
            if pair in seen_source_edges:
                errors.append(f"tree {tree_id} source edge {index}: duplicate edge")
            seen_source_edges.add(pair)
            for endpoint in pair:
                if endpoint not in tree_node_ids:
                    errors.append(
                        f"tree {tree_id} source edge {index}: unknown local research id {endpoint}"
                    )
            if prerequisite_id == research_id:
                errors.append(f"tree {tree_id} source edge {index}: self edge")
            errors.extend(
                _verification_errors(
                    edge.get("verification"),
                    f"tree {tree_id} source edge {index}.verification",
                    known_sources,
                    known_evidence,
                )
            )

        seen_connections: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        for index, connection in enumerate(tree.get("display_connections", [])):
            from_ids = tuple(str(item) for item in connection.get("from_ids", []))
            to_ids = tuple(str(item) for item in connection.get("to_ids", []))
            key = (from_ids, to_ids)
            if not from_ids or not to_ids:
                errors.append(f"tree {tree_id} connection {index}: empty endpoint")
            if key in seen_connections:
                errors.append(f"tree {tree_id} connection {index}: duplicate connection")
            seen_connections.add(key)
            for research_id in (*from_ids, *to_ids):
                if research_id not in tree_node_ids:
                    errors.append(
                        f"tree {tree_id} connection {index}: unknown local research id {research_id}"
                    )
            if set(from_ids) & set(to_ids):
                errors.append(f"tree {tree_id} connection {index}: self connection")
            errors.extend(
                _verification_errors(
                    connection.get("verification"),
                    f"tree {tree_id} connection {index}.verification",
                    known_sources,
                    known_evidence,
                )
            )

    for research_id, node in nodes.items():
        maximum = int(node.get("max_level") or 0)
        for level in node.get("levels", []):
            level_number = level.get("level")
            if not isinstance(level_number, int) or not 1 <= level_number <= maximum:
                continue
            for requirement in level.get("prerequisites", []):
                prerequisite_id = str(requirement.get("research_id", ""))
                prerequisite_level = requirement.get("level")
                prerequisite = nodes.get(prerequisite_id)
                if prerequisite is None:
                    errors.append(
                        f"research {research_id} level {level_number}: unknown prerequisite {prerequisite_id}"
                    )
                    continue
                if (
                    not isinstance(prerequisite_level, int)
                    or not 1
                    <= prerequisite_level
                    <= int(prerequisite.get("max_level") or 0)
                ):
                    errors.append(
                        f"research {research_id} level {level_number}: invalid prerequisite level"
                    )
                    continue
                dependency = (prerequisite_id, prerequisite_level)
                current = (research_id, level_number)
                if dependency == current:
                    errors.append(
                        f"research {research_id} level {level_number}: self prerequisite"
                    )
                graph[current].add(dependency)

    errors.extend(_cycle_errors(graph))

    aliases = aliases_document.get("aliases", {})
    if not isinstance(aliases, dict):
        errors.append("aliases: aliases must be an object")
        aliases = {}
    for old_id, new_id in aliases.items():
        if old_id in nodes:
            errors.append(f"aliases: active research id cannot be an alias: {old_id}")
        if old_id == new_id:
            errors.append(f"aliases: identity alias is not allowed: {old_id}")
        visited = {old_id}
        target = new_id
        while target in aliases:
            if target in visited:
                errors.append(f"aliases: cycle detected at {old_id}")
                break
            visited.add(target)
            target = aliases[target]
        else:
            if target not in nodes:
                errors.append(f"aliases: target does not resolve to active research: {old_id}")

    for locale, document in locales.items():
        if document.get("locale") != locale:
            errors.append(f"locale {locale}: document locale does not match manifest")
        tree_names = set((document.get("trees") or {}).keys())
        research_names = set((document.get("research") or {}).keys())
        metric_names = set((document.get("metrics") or {}).keys())
        if tree_names - set(trees):
            errors.append(f"locale {locale}: contains unknown tree IDs")
        if research_names - set(nodes):
            errors.append(f"locale {locale}: contains unknown research IDs")
        if locale in required_locales:
            if set(trees) - tree_names:
                errors.append(f"locale {locale}: required tree translations are missing")
            if set(nodes) - research_names:
                errors.append(f"locale {locale}: required research translations are missing")
            if metric_ids - metric_names:
                errors.append(f"locale {locale}: required metric translations are missing")
    return sorted(set(errors))


def collect_data_quality_warnings(documents: dict[str, Any]) -> list[dict[str, Any]]:
    """Return suspicious, but not universally invalid, level-value reversals.

    Game data can legitimately contain exceptional progressions, so these are
    review warnings rather than validation failures. Keeping them structured
    makes every exception visible without silently normalizing source values.
    """

    warnings: list[dict[str, Any]] = []
    for tree_id, tree in sorted(documents.get("trees", {}).items()):
        rows = {
            str(node.get("id") or ""): int(node.get("layout", {}).get("row") or 0)
            for node in tree.get("nodes", [])
        }
        for node in sorted(tree.get("nodes", []), key=lambda item: item.get("id", "")):
            previous: dict[str, tuple[int, int]] = {}
            for level in sorted(
                node.get("levels", []),
                key=lambda item: int(item.get("level") or 0),
            ):
                level_number = int(level.get("level") or 0)
                values = {
                    "academy_level": level.get("academy_level"),
                    "base_time_seconds": level.get("base_time_seconds"),
                    "power": level.get("power"),
                }
                costs = level.get("costs")
                if isinstance(costs, dict):
                    if not costs:
                        warnings.append(
                            {
                                "code": "empty_verified_costs",
                                "tree_id": tree_id,
                                "research_id": str(node.get("id") or ""),
                                "level": level_number,
                                "field": "costs",
                            }
                        )
                    values.update(
                        {f"costs.{resource_id}": amount for resource_id, amount in costs.items()}
                    )
                for field, value in sorted(values.items()):
                    if not isinstance(value, int):
                        continue
                    prior = previous.get(field)
                    if prior is not None and value < prior[1]:
                        warnings.append(
                            {
                                "code": "level_value_decreased",
                                "tree_id": tree_id,
                                "research_id": str(node.get("id") or ""),
                                "level": level_number,
                                "field": field,
                                "previous_level": prior[0],
                                "previous_value": prior[1],
                                "value": value,
                            }
                        )
                    previous[field] = (level_number, value)
        for index, connection in enumerate(tree.get("display_connections", [])):
            for prerequisite_id in connection.get("from_ids", []):
                for research_id in connection.get("to_ids", []):
                    if rows.get(str(prerequisite_id), 0) > rows.get(str(research_id), 0):
                        warnings.append(
                            {
                                "code": "display_connection_reverses_rows",
                                "tree_id": tree_id,
                                "connection_index": index,
                                "prerequisite_id": str(prerequisite_id),
                                "research_id": str(research_id),
                                "prerequisite_row": rows.get(str(prerequisite_id), 0),
                                "research_row": rows.get(str(research_id), 0),
                            }
                        )
    return warnings


def _cycle_errors(
    graph: dict[tuple[str, int], set[tuple[str, int]]],
) -> list[str]:
    dependents: dict[tuple[str, int], set[tuple[str, int]]] = defaultdict(set)
    remaining = {node: len(dependencies) for node, dependencies in graph.items()}
    for node, dependencies in graph.items():
        for dependency in dependencies:
            dependents[dependency].add(node)
            remaining.setdefault(dependency, 0)
    ready = deque(sorted(node for node, count in remaining.items() if count == 0))
    resolved = 0
    while ready:
        node = ready.popleft()
        resolved += 1
        for dependent in sorted(dependents.get(node, ())):
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                ready.append(dependent)
    if resolved == len(remaining):
        return []
    cyclic = min(node for node, count in remaining.items() if count > 0)
    return [f"prerequisites: cycle detected at {cyclic[0]}:{cyclic[1]}"]


def validate_dataset(root: Path) -> list[str]:
    try:
        documents = load_dataset(root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return [str(exc)]
    return [
        *validate_schema_documents(),
        *validate_schema_instances(documents),
        *validate_documents(documents),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an RLM research dataset")
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    errors = validate_dataset(args.root)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"Dataset validation passed: {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
