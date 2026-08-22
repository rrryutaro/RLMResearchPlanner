from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rlm_research_planner.services.language_pack import (
    LANGUAGE_PACK_SECTIONS,
    load_bundled_locale_manifest,
)


MONOREPO_PWA_ROOT = ROOT.parent / "RLMResearchPlannerPWA"
PUBLIC_PWA_ROOT = ROOT / "tools" / "RLMResearchPlannerPWA"
PWA_ROOT = (
    MONOREPO_PWA_ROOT
    if (MONOREPO_PWA_ROOT / "index.html").is_file()
    else PUBLIC_PWA_ROOT
)
PYTHON_MESSAGE_CALL = re.compile(r"self\.t\(\s*[\"']([^\"']+)[\"']")
JAVASCRIPT_MESSAGE_CALL = re.compile(r"(?<![\w.])t\(\s*[\"']([^\"']+)[\"']")
STATIC_ATTRIBUTE = re.compile(
    r"data-i18n(?:-placeholder|-title|-aria)?=[\"']([^\"']+)[\"']"
)
FORBIDDEN_RUNTIME_PATTERNS = (
    re.compile(r"startsWith\(\s*[\"']ja"),
    re.compile(r"startswith\(\s*[\"']ja"),
    re.compile(r"locale\s*={2,3}\s*[\"']ja(?:-JP)?[\"']"),
    re.compile(r"\[\s*[\"']ja-JP[\"']\s*,\s*[\"']en-US[\"']"),
)


def source_text(root: Path, suffix: str) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(root.rglob(f"*{suffix}"))
    )


def main() -> int:
    manifest = load_bundled_locale_manifest(ROOT / "resources" / "i18n")
    fallback = manifest.by_locale[manifest.fallback_locale].pack
    errors: list[str] = []

    python_source = source_text(ROOT / "src", ".py")
    javascript_source = source_text(PWA_ROOT / "src", ".js")
    html_source = (PWA_ROOT / "index.html").read_text(encoding="utf-8")
    runtime_source = f"{python_source}\n{javascript_source}"
    used_messages = set(PYTHON_MESSAGE_CALL.findall(python_source))
    used_messages.update(JAVASCRIPT_MESSAGE_CALL.findall(javascript_source))
    used_messages.update(STATIC_ATTRIBUTE.findall(html_source))
    missing_messages = sorted(
        used_messages - set(fallback.sections.get("messages", {}))
    )
    if missing_messages:
        errors.append(
            "Fallback language pack is missing UI keys: "
            + ", ".join(missing_messages)
        )

    for entry in manifest.locales:
        missing_sections = [
            section
            for section in LANGUAGE_PACK_SECTIONS
            if section not in entry.pack.sections
        ]
        if missing_sections:
            errors.append(
                f"{entry.locale}: missing language-pack sections: "
                + ", ".join(missing_sections)
            )
        missing_bundled_messages = sorted(
            set(fallback.sections.get("messages", {}))
            - set(entry.pack.sections.get("messages", {}))
        )
        if missing_bundled_messages:
            errors.append(
                f"{entry.locale}: missing bundled UI keys: "
                + ", ".join(missing_bundled_messages)
            )

    for pattern in FORBIDDEN_RUNTIME_PATTERNS:
        if match := pattern.search(runtime_source):
            errors.append(
                "Runtime language-specific branch is forbidden: " + match.group(0)
            )

    pwa_manifest = json.loads(
        (PWA_ROOT / "data" / "i18n" / "manifest.json").read_text(encoding="utf-8")
    )
    desktop_manifest = json.loads(
        (ROOT / "resources" / "i18n" / "manifest.json").read_text(encoding="utf-8")
    )
    if pwa_manifest != desktop_manifest:
        errors.append("Desktop and PWA locale manifests are not synchronized.")
    for entry in desktop_manifest.get("locales", []):
        filename = str(entry.get("path", ""))
        desktop_path = ROOT / "resources" / "i18n" / filename
        pwa_path = PWA_ROOT / "data" / "i18n" / filename
        if not pwa_path.is_file() or json.loads(
            pwa_path.read_text(encoding="utf-8-sig")
        ) != json.loads(desktop_path.read_text(encoding="utf-8-sig")):
            errors.append(f"Desktop and PWA language pack differ: {filename}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        f"Language coverage passed: {len(manifest.locales)} bundled locales, "
        f"{len(used_messages)} referenced UI keys."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
