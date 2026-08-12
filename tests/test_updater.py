from __future__ import annotations

from rlm_research_planner.services import updater
from rlm_research_planner.settings import AppSettings
from rlm_research_planner.version import version_string


def test_current_release_version_hides_internal_build_number() -> None:
    assert version_string() == "0.1.2"


def test_version_comparison_uses_numeric_components() -> None:
    assert updater.parse_version("v0.0.10") == (0, 0, 10)
    assert updater.is_newer_version("0.1.0", "0.0.99")
    assert not updater.is_newer_version("v0.0.1", "0.0.1")


def test_release_parser_selects_latest_non_draft_release_including_prerelease() -> None:
    payload = [
        {
            "tag_name": "v0.0.5",
            "draft": True,
            "prerelease": False,
            "assets": [],
        },
        {
            "tag_name": "v0.0.4",
            "draft": False,
            "prerelease": True,
            "body": "Latest Alpha release",
            "html_url": "https://example.invalid/releases/v0.0.4",
            "assets": [
                {
                    "name": updater.APP_EXECUTABLE_NAME,
                    "browser_download_url": "https://example.invalid/app.exe",
                    "size": 123,
                },
                {
                    "name": updater.CHECKSUM_ASSET_NAME,
                    "browser_download_url": "https://example.invalid/app.sha256",
                    "size": 100,
                },
            ],
        },
        {
            "tag_name": "v0.0.3",
            "draft": False,
            "prerelease": False,
            "body": "Latest stable release",
            "html_url": "https://example.invalid/releases/v0.0.3",
            "assets": [
                {
                    "name": updater.APP_EXECUTABLE_NAME,
                    "browser_download_url": "https://example.invalid/app.exe",
                    "size": 123,
                },
                {
                    "name": updater.CHECKSUM_ASSET_NAME,
                    "browser_download_url": "https://example.invalid/app.sha256",
                    "size": 100,
                },
            ],
        },
        {
            "tag_name": "v0.0.1",
            "draft": False,
            "prerelease": False,
            "assets": [],
        },
    ]

    release = updater.parse_releases_payload(payload)

    assert release is not None
    assert release.version == "0.0.4"
    assert release.tag == "v0.0.4"
    assert release.body == "Latest Alpha release"
    assert release.asset(updater.APP_EXECUTABLE_NAME).size == 123
    assert not updater.auto_update_unavailable_reason(release) or (
        updater.distribution_type() != "onefile"
    )


def test_checksum_parser_accepts_standard_sha256_file_format() -> None:
    digest = "a" * 64

    assert (
        updater.parse_checksum(f"{digest}  {updater.APP_EXECUTABLE_NAME}\n")
        == digest
    )


def test_checksum_parser_rejects_wrong_asset_name() -> None:
    digest = "b" * 64

    try:
        updater.parse_checksum(f"{digest}  different.exe\n")
    except ValueError:
        pass
    else:
        raise AssertionError("A checksum for a different asset was accepted.")


def test_helper_script_replaces_stable_executable_and_restarts() -> None:
    script = updater.generate_helper_script()

    assert updater.APP_EXECUTABLE_NAME in script
    assert updater.STAGED_EXECUTABLE_NAME in script
    assert updater.BACKUP_EXECUTABLE_NAME in script
    assert "--updated" in script
    assert 'del "%~f0"' in script


def test_update_preferences_have_safe_defaults() -> None:
    settings = AppSettings()

    assert settings.update_check_on_startup is True
    assert settings.update_skipped_version == ""
