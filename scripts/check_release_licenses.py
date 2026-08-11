from __future__ import annotations

import importlib.metadata
import json
import os
import re
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


def _match(pattern: str, text: str, description: str, errors: list[str]) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        errors.append(f"Cannot read {description}.")
        return ""
    return match.group(1)


def _python_notice_errors(
    notices: str,
    *,
    running_version: str,
    exact_runtime: bool,
) -> list[str]:
    errors: list[str] = []
    version_parts = running_version.split(".")
    version_series = ".".join(version_parts[:2])
    if not re.search(rf"\bPython {re.escape(version_series)}\.\d+\b", notices):
        errors.append(
            "THIRD_PARTY_NOTICES.md does not cover the validation Python "
            f"{version_series} series."
        )
    elif exact_runtime and f"Python {running_version}" not in notices:
        errors.append(
            "THIRD_PARTY_NOTICES.md does not match the final build Python "
            f"{running_version}."
        )
    return errors


def _report_error(error: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        escaped = error.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Release license check::{escaped}", file=sys.stderr)
        return
    print(f"ERROR: {error}", file=sys.stderr)


def check(
    *,
    final: bool = False,
    exact_runtime: bool = False,
) -> list[str]:
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
    if _load_json(pwa_research) != research:
        errors.append("The PWA research catalog is not synchronized.")
    if _load_json(pwa_castle) != castle:
        errors.append("The PWA castle catalog is not synchronized.")

    package_versions = {
        "PySide6": importlib.metadata.version("PySide6"),
        "Shiboken6": importlib.metadata.version("shiboken6"),
        "PyInstaller": importlib.metadata.version("PyInstaller"),
    }
    for package, version in package_versions.items():
        if f"{package} {version}" not in notices:
            errors.append(
                f"THIRD_PARTY_NOTICES.md does not match installed {package} {version}."
            )
    running_python = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    errors.extend(
        _python_notice_errors(
            notices,
            running_version=running_python,
            exact_runtime=exact_runtime,
        )
    )

    pwa_index = (PWA_ROOT / "index.html").read_text(encoding="utf-8")
    if 'rel="license"' not in pwa_index or "DATA_LICENSE.md" not in pwa_index:
        errors.append("The PWA document does not expose data-license metadata.")

    desktop_version_source = (
        PRODUCT_ROOT / "src" / "rlm_research_planner" / "version.py"
    ).read_text(encoding="utf-8")
    desktop_version = _match(
        r'^__version__\s*=\s*"([^"]+)"',
        desktop_version_source,
        "desktop version",
        errors,
    )
    desktop_build = _match(
        r"^__build__\s*=\s*(\d+)",
        desktop_version_source,
        "desktop build number",
        errors,
    )
    desktop_is_development = _match(
        r"^__dev__\s*=\s*(True|False)",
        desktop_version_source,
        "desktop release status",
        errors,
    )
    project_source = (PRODUCT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_version = _match(
        r'^version\s*=\s*"([^"]+)"',
        project_source,
        "pyproject version",
        errors,
    )
    if desktop_version and desktop_version != project_version:
        errors.append("Desktop version.py and pyproject.toml do not match.")

    version_info_path = PRODUCT_ROOT / "resources" / "windows_version_info.txt"
    if not version_info_path.is_file():
        errors.append("Missing Windows executable version metadata.")
    elif desktop_version:
        version_info = version_info_path.read_text(encoding="utf-8")
        version_tuple = ", ".join(desktop_version.split(".")) + ", 0"
        if f"filevers=({version_tuple})" not in version_info:
            errors.append("Windows FileVersion tuple does not match the desktop version.")
        if f"StringStruct('FileVersion', '{desktop_version}')" not in version_info:
            errors.append("Windows FileVersion text does not match the desktop version.")
        if f"StringStruct('ProductVersion', '{desktop_version}')" not in version_info:
            errors.append("Windows ProductVersion text does not match the desktop version.")
    build_script = (PRODUCT_ROOT / "build_exe.bat").read_text(encoding="utf-8")
    if '--version-file "%~dp0resources\\windows_version_info.txt"' not in build_script:
        errors.append("The executable build does not include Windows version metadata.")
    if 'PYINSTALLER_CONFIG_DIR=%~dp0..\\..\\build\\PyInstallerCache' not in build_script:
        errors.append("The executable build does not keep the PyInstaller cache local.")
    if "scripts\\write_release_checksum.py" not in build_script:
        errors.append("The executable build does not create the SHA-256 asset.")
    if '--add-data "%~dp0data;data"' in build_script:
        errors.append(
            "The executable build includes the private data directory wholesale."
        )
    required_public_data = (
        r'data\buildings;data\buildings',
        r'data\ocr;data\ocr',
        r'data\research\catalog.json;data\research',
        r'data\research\master.json;data\research',
        r'data\research\locales;data\research\locales',
    )
    for entry in required_public_data:
        if entry not in build_script:
            errors.append(f"The executable build is missing public data: {entry}")

    pwa_version_source = (PWA_ROOT / "version.py").read_text(encoding="utf-8")
    pwa_version = _match(
        r'^__version__\s*=\s*"([^"]+)"',
        pwa_version_source,
        "PWA version",
        errors,
    )
    pwa_build = _match(
        r"^__build__\s*=\s*(\d+)",
        pwa_version_source,
        "PWA build number",
        errors,
    )
    pwa_is_development = _match(
        r"^__dev__\s*=\s*(True|False)",
        pwa_version_source,
        "PWA release status",
        errors,
    )
    package_version = str(_load_json(PWA_ROOT / "package.json").get("version", ""))
    expected_package_version = pwa_version
    if expected_package_version and package_version != expected_package_version:
        errors.append(
            "PWA package version must match the release version without a build number."
        )
    pwa_app = (PWA_ROOT / "src" / "app.js").read_text(encoding="utf-8")
    if pwa_version and f'RELEASE_VERSION = "{pwa_version}"' not in pwa_app:
        errors.append("PWA app release version does not match version.py.")
    if pwa_build and f"DEVELOPMENT_BUILD = {pwa_build}" not in pwa_app:
        errors.append("PWA app build number does not match version.py.")
    asset_version = f"{pwa_version}-b{pwa_build}"
    if pwa_version and pwa_build:
        if f"styles.css?v={asset_version}" not in pwa_index:
            errors.append("PWA index asset version does not match version.py.")
        pwa_worker = (PWA_ROOT / "sw.js").read_text(encoding="utf-8")
        if f"v{asset_version}" not in pwa_worker:
            errors.append("PWA Service Worker cache version does not match version.py.")

    if desktop_version and pwa_version and desktop_version != pwa_version:
        errors.append("Desktop and PWA release versions do not match.")
    if final and desktop_is_development != "False":
        errors.append("Desktop version is still marked as a development build.")
    if final and pwa_is_development != "False":
        errors.append("PWA version is still marked as a development build.")
    return errors


def main() -> int:
    arguments = set(sys.argv[1:])
    errors = check(
        final="--final" in arguments,
        exact_runtime="--exact-runtime" in arguments,
    )
    if errors:
        for error in errors:
            _report_error(error)
        return 1
    print("Release license checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
