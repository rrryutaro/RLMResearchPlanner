from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "scripts"))

from validate_dataset import load_dataset, validate_dataset  # noqa: E402


SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?$")
FORBIDDEN_TRANSLATION_KEYS = {
    "name",
    "names",
    "title",
    "titles",
    "display_name",
    "localized_names",
}


def _translation_keys(value: Any, path: str = "") -> list[str]:
    failures: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            if key in FORBIDDEN_TRANSLATION_KEYS:
                failures.append(child)
            failures.extend(_translation_keys(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(_translation_keys(item, f"{path}[{index}]"))
    return failures


def check_distribution(root: Path) -> list[str]:
    errors = list(validate_dataset(root))
    documents = load_dataset(root)
    version = str(documents["manifest"].get("dataset_version") or "")
    if not SEMVER.fullmatch(version):
        errors.append(f"manifest.dataset_version is not SemVer: {version}")
    if not (PACKAGE_ROOT / "DATA_LICENSE.md").is_file():
        errors.append("DATA_LICENSE.md is missing from the dataset package")
    if not (PACKAGE_ROOT / "CONTRIBUTING.md").is_file():
        errors.append("CONTRIBUTING.md is missing from the dataset package")
    for tree_id, tree in documents["trees"].items():
        for path in _translation_keys(tree):
            errors.append(f"tree {tree_id} contains localized display field: {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a distributable RLM research dataset")
    parser.add_argument("root", nargs="?", type=Path, default=PACKAGE_ROOT / "generated")
    args = parser.parse_args()
    errors = check_distribution(args.root)
    if errors:
        print("Research dataset distribution check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    manifest = json.loads((args.root / "manifest.json").read_text(encoding="utf-8"))
    print(f"Research dataset distribution check passed: {manifest['dataset_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
