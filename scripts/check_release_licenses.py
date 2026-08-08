from __future__ import annotations

import importlib.metadata
import json
import sys
from pathlib import Path


PRODUCT_ROOT = Path(__file__).resolve().parents[1]


def _pwa_root() -> Path:
    development_path = PRODUCT_ROOT.parent / "RLMResearchPlannerPWA"
    public_repository_path = PRODUCT_ROOT / "tools" / "RLMResearchPlannerPWA"
    if development_path.is_dir():
        return development_path
    return public_repository_path


PWA_ROOT = _pwa_root()

REQUIRED_FILES = (
    Path("LICENSE"),
    Path("DATA_LICENSE.md"),
    Path("licenses/THIRD_PARTY_NOTICES.md"),
    Path("licenses/GPL-3.0.txt"),
    Path("licenses/LGPL-3.0.txt"),
    Path("licenses/PyInstaller-COPYING.txt"),
    Path("licenses/Python-3.12-LICENSE.txt"),
)


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_urls(catalog: dict[str, object], collection: str) -> set[str]:
    urls: set[str] = set()
    for source in catalog.get("sources", []):
        if isinstance(source, str):
            urls.add(source)
        elif isinstance(source, dict) and source.get("url"):
            urls.add(str(source["url"]))
    for item in catalog.get(collection, []):
        if isinstance(item, dict) and item.get("source_url"):
            urls.add(str(item["source_url"]))
    return urls


def check() -> list[str]:
    errors: list[str] = []
    for relative_path in REQUIRED_FILES:
        if not (PRODUCT_ROOT / relative_path).is_file():
            errors.append(f"Missing release license file: {relative_path.as_posix()}")

    data_license_path = PRODUCT_ROOT / "DATA_LICENSE.md"
    notices_path = PRODUCT_ROOT / "licenses" / "THIRD_PARTY_NOTICES.md"
    if not data_license_path.is_file() or not notices_path.is_file():
        return errors

    data_license = data_license_path.read_text(encoding="utf-8")
    notices = notices_path.read_text(encoding="utf-8")
    if "CC BY-SA 3.0 Unported" not in data_license:
        errors.append("DATA_LICENSE.md must identify CC BY-SA 3.0 Unported.")

    research_path = PRODUCT_ROOT / "data" / "research" / "catalog.json"
    castle_path = PRODUCT_ROOT / "data" / "buildings" / "castle_catalog.json"
    research = _load_json(research_path)
    castle = _load_json(castle_path)
    urls = _source_urls(research, "categories") | _source_urls(castle, "buildings")
    for url in sorted(urls):
        if url not in data_license:
            errors.append(f"DATA_LICENSE.md is missing source attribution: {url}")

    pwa_research = PWA_ROOT / "data" / "research" / "catalog.json"
    pwa_castle = PWA_ROOT / "data" / "buildings" / "castle_catalog.json"
    if pwa_research.read_bytes() != research_path.read_bytes():
        errors.append("The PWA research catalog is not synchronized.")
    if pwa_castle.read_bytes() != castle_path.read_bytes():
        errors.append("The PWA castle catalog is not synchronized.")

    package_versions = {
        "PySide6": importlib.metadata.version("PySide6"),
        "Shiboken6": importlib.metadata.version("shiboken6"),
        "PyInstaller": importlib.metadata.version("PyInstaller"),
        "Python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }
    for package, version in package_versions.items():
        if f"{package} {version}" not in notices:
            errors.append(
                f"THIRD_PARTY_NOTICES.md does not match installed {package} {version}."
            )

    pwa_index = (PWA_ROOT / "index.html").read_text(encoding="utf-8")
    if 'rel="license"' not in pwa_index or "DATA_LICENSE.md" not in pwa_index:
        errors.append("The PWA document does not expose data-license metadata.")
    return errors


def main() -> int:
    errors = check()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Release license checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
