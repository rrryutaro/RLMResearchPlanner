from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = PROJECT_ROOT / "dataset"
SCRIPTS_ROOT = DATASET_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS_ROOT))

from compare_legacy_and_generated import build_comparison  # noqa: E402
from convert_legacy_catalog import (  # noqa: E402
    OUTPUT_ROOT,
    build_generated_dataset,
    write_generated_dataset,
)
from validate_dataset import validate_dataset  # noqa: E402


REPORT_PATH = DATASET_ROOT / "reports" / "legacy-vs-generated.json"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    generated = build_generated_dataset()
    write_generated_dataset(generated, OUTPUT_ROOT)

    errors = validate_dataset(OUTPUT_ROOT)
    if errors:
        print("Research dataset validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    report = build_comparison(OUTPUT_ROOT)
    _write_json(REPORT_PATH, report)
    if report["status"] != "match":
        print("Legacy compatibility comparison failed:")
        for difference in report["differences"]:
            print(f"- {difference}")
        return 1

    statistics = report["statistics"]
    print(
        "Research dataset refreshed and verified: "
        f"{statistics['categories']} trees, {statistics['research']} research IDs, "
        f"{statistics['levels']} level records, "
        f"{statistics['representative_plans']} representative plans, 0 differences, "
        f"{statistics['data_quality_warnings']} review warnings."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
