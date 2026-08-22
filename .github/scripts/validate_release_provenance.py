from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_VALIDATIONS = {
    "dataset_distribution",
    "language_coverage",
    "desktop_tests",
    "release_pipeline_tests",
    "pwa_source",
    "pwa_tests",
    "pwa_release_layout",
}
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    errors: list[str] = []
    path = ROOT / "release-provenance.json"
    if not path.is_file():
        print("release-provenance.json is missing", file=sys.stderr)
        return 1
    document = json.loads(path.read_text(encoding="utf-8"))
    version = str(document.get("version", ""))
    if document.get("schema_version") != 1:
        errors.append("unsupported provenance schema")
    if document.get("product") != "RLMResearchPlanner":
        errors.append("unexpected product")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("invalid release version")
    for key in ("private_commit", "source_tree", "public_parent"):
        if not HEX_40.fullmatch(str(document.get(key, ""))):
            errors.append(f"invalid {key}")
    for key in ("release_notes_sha256", "executable_sha256"):
        if not HEX_64.fullmatch(str(document.get(key, ""))):
            errors.append(f"invalid {key}")
    validations = document.get("validation", {})
    if set(validations) != REQUIRED_VALIDATIONS:
        errors.append("required validation set does not match")
    elif any(status != "passed" for status in validations.values()):
        errors.append("a local release validation did not pass")
    notes = ROOT / "Document" / f"ReleaseNotes-v{version}.md"
    if not notes.is_file():
        errors.append("release notes are missing")
    elif sha256(notes) != document.get("release_notes_sha256"):
        errors.append("release notes changed after preparation")
    desktop_source = (
        ROOT / "src" / "rlm_research_planner" / "version.py"
    ).read_text(encoding="utf-8")
    pwa = json.loads(
        (ROOT / "tools" / "RLMResearchPlannerPWA" / "package.json").read_text(
            encoding="utf-8"
        )
    )
    if f'__version__ = "{version}"' not in desktop_source:
        errors.append("desktop version differs from provenance")
    if pwa.get("version") != version:
        errors.append("PWA version differs from provenance")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"Release provenance is valid for v{version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
