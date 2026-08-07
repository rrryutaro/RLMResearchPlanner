from __future__ import annotations

import hashlib
import json
import os
import ssl
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from rlm_research_planner.version import __dev__, __version__


GITHUB_OWNER = "rrryutaro"
GITHUB_REPOSITORY = "RLMResearchPlanner"
RELEASE_TAG_PREFIX = "v"
RELEASES_API_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases"
)
RELEASES_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases"
APP_EXECUTABLE_NAME = "RLMResearchPlanner.exe"
CHECKSUM_ASSET_NAME = f"{APP_EXECUTABLE_NAME}.sha256"
STAGED_EXECUTABLE_NAME = "RLMResearchPlanner_new.exe"
BACKUP_EXECUTABLE_NAME = "RLMResearchPlanner_old.exe"
UPDATE_HELPER_NAME = "RLMResearchPlanner_update.cmd"
USER_AGENT = "RLMResearchPlanner-Updater"


class UpdateCancelledError(Exception):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int | None = None


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    body: str
    html_url: str
    assets: dict[str, ReleaseAsset]

    def asset(self, name: str) -> ReleaseAsset | None:
        return self.assets.get(name)


def parse_version(value: object) -> tuple[int, ...]:
    if value is None:
        return ()
    text = str(value).strip()
    if text.startswith(RELEASE_TAG_PREFIX):
        text = text[len(RELEASE_TAG_PREFIX) :]
    values: list[int] = []
    for part in text.split("."):
        digits = ""
        for character in part:
            if not character.isdigit():
                break
            digits += character
        if not digits:
            break
        values.append(int(digits))
    return tuple(values)


def is_newer_version(latest: object, current: object = __version__) -> bool:
    return parse_version(latest) > parse_version(current)


def parse_releases_payload(payload: object) -> ReleaseInfo | None:
    if not isinstance(payload, list):
        return None
    best_release: dict[str, object] | None = None
    best_version: tuple[int, ...] = ()
    for candidate in payload:
        if not isinstance(candidate, dict):
            continue
        tag = str(candidate.get("tag_name", ""))
        if not tag.startswith(RELEASE_TAG_PREFIX):
            continue
        if candidate.get("draft") or candidate.get("prerelease"):
            continue
        version = parse_version(tag)
        if version > best_version:
            best_release = candidate
            best_version = version
    if best_release is None:
        return None

    assets: dict[str, ReleaseAsset] = {}
    raw_assets = best_release.get("assets", [])
    if isinstance(raw_assets, list):
        for raw_asset in raw_assets:
            if not isinstance(raw_asset, dict):
                continue
            name = str(raw_asset.get("name", "")).strip()
            url = str(raw_asset.get("browser_download_url", "")).strip()
            if not name or not url:
                continue
            raw_size = raw_asset.get("size")
            try:
                size = int(raw_size) if raw_size is not None else None
            except (TypeError, ValueError):
                size = None
            assets[name] = ReleaseAsset(name=name, url=url, size=size)

    version_text = ".".join(str(number) for number in best_version)
    return ReleaseInfo(
        version=version_text,
        tag=str(best_release.get("tag_name", "")),
        body=str(best_release.get("body", "") or ""),
        html_url=str(best_release.get("html_url", "") or ""),
        assets=assets,
    )


def distribution_type() -> str:
    if not getattr(sys, "frozen", False):
        return "source"
    executable_directory = Path(sys.executable).resolve().parent
    bundle_directory = Path(getattr(sys, "_MEIPASS", executable_directory)).resolve()
    try:
        bundle_directory.relative_to(executable_directory)
    except ValueError:
        return "onefile"
    return "folder"


def update_checks_enabled() -> bool:
    return distribution_type() == "onefile" and not __dev__


def install_directory() -> Path:
    return Path(sys.executable).resolve().parent


def _open_url(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(
        request,
        timeout=timeout,
        context=ssl.create_default_context(),
    ) as response:
        return response.read()


def get_latest_release(timeout: int = 10) -> ReleaseInfo | None:
    payload = json.loads(_open_url(RELEASES_API_URL, timeout).decode("utf-8"))
    return parse_releases_payload(payload)


def check_for_update(timeout: int = 10) -> ReleaseInfo | None:
    if not update_checks_enabled():
        return None
    latest = get_latest_release(timeout)
    if latest is None or not is_newer_version(latest.version):
        return None
    return latest


def auto_update_unavailable_reason(release: ReleaseInfo) -> str:
    if distribution_type() != "onefile":
        return "distribution"
    if release.asset(APP_EXECUTABLE_NAME) is None:
        return "executable"
    if release.asset(CHECKSUM_ASSET_NAME) is None:
        return "checksum"
    return ""


def sha256_file(path: Path, buffer_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(buffer_size):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksum(text: str, executable_name: str = APP_EXECUTABLE_NAME) -> str:
    for line in text.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        candidate = parts[0].lower()
        if len(candidate) != 64 or any(ch not in "0123456789abcdef" for ch in candidate):
            continue
        if len(parts) == 1:
            return candidate
        filename = parts[-1].lstrip("*")
        if Path(filename).name.casefold() == executable_name.casefold():
            return candidate
    raise ValueError("The release checksum file is invalid.")


def _cancelled(cancel_event: Event | None) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def _download_file(
    asset: ReleaseAsset,
    destination: Path,
    *,
    expected_sha256: str,
    progress_callback: Callable[[int, int | None], None] | None = None,
    cancel_event: Event | None = None,
    timeout: int = 120,
) -> Path:
    partial = destination.with_name(f"{destination.name}.part")
    request = urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT})
    downloaded = 0
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=ssl.create_default_context(),
        ) as response:
            total = asset.size
            if total is None:
                try:
                    total = int(response.headers.get("Content-Length"))
                except (TypeError, ValueError):
                    total = None
            with partial.open("wb") as stream:
                while True:
                    if _cancelled(cancel_event):
                        raise UpdateCancelledError()
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    stream.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None:
                        progress_callback(downloaded, total)
        if asset.size is not None and partial.stat().st_size != asset.size:
            raise ValueError("The downloaded file size does not match the release asset.")
        if sha256_file(partial) != expected_sha256.lower():
            raise ValueError("The downloaded executable checksum does not match.")
        partial.replace(destination)
        return destination
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def stage_update(
    release: ReleaseInfo,
    directory: Path,
    *,
    progress_callback: Callable[[int, int | None], None] | None = None,
    cancel_event: Event | None = None,
) -> Path:
    executable_asset = release.asset(APP_EXECUTABLE_NAME)
    checksum_asset = release.asset(CHECKSUM_ASSET_NAME)
    if executable_asset is None or checksum_asset is None:
        raise ValueError("The release does not contain all automatic-update assets.")
    if _cancelled(cancel_event):
        raise UpdateCancelledError()
    checksum_text = _open_url(checksum_asset.url, timeout=30).decode("utf-8-sig")
    expected_sha256 = parse_checksum(checksum_text)
    destination = directory / STAGED_EXECUTABLE_NAME
    return _download_file(
        executable_asset,
        destination,
        expected_sha256=expected_sha256,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )


def has_write_permission(directory: Path) -> bool:
    probe = directory / ".rlm_update_write_test"
    try:
        probe.write_bytes(b"1")
        probe.unlink()
        return True
    except OSError:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def generate_helper_script() -> str:
    return "\r\n".join(
        (
            "@echo off",
            "setlocal enableextensions",
            'cd /d "%~dp0"',
            "set /a attempts=0",
            ":wait_for_exit",
            f'move /Y "{APP_EXECUTABLE_NAME}" "{BACKUP_EXECUTABLE_NAME}" >NUL 2>NUL',
            f'if not exist "{APP_EXECUTABLE_NAME}" goto install_update',
            "set /a attempts+=1",
            "if %attempts% GEQ 150 goto restore_and_exit",
            "ping -n 2 127.0.0.1 >NUL",
            "goto wait_for_exit",
            ":install_update",
            f'move /Y "{STAGED_EXECUTABLE_NAME}" "{APP_EXECUTABLE_NAME}" >NUL 2>NUL',
            f'if not exist "{APP_EXECUTABLE_NAME}" goto restore_and_exit',
            "ping -n 3 127.0.0.1 >NUL",
            f'start "" "{APP_EXECUTABLE_NAME}" --updated',
            "goto cleanup",
            ":restore_and_exit",
            f'if not exist "{APP_EXECUTABLE_NAME}" if exist "{BACKUP_EXECUTABLE_NAME}" move /Y "{BACKUP_EXECUTABLE_NAME}" "{APP_EXECUTABLE_NAME}" >NUL 2>NUL',
            ":cleanup",
            'del "%~f0"',
            "",
        )
    )


def launch_update_helper(directory: Path) -> Path:
    helper_path = directory / UPDATE_HELPER_NAME
    helper_path.write_text(generate_helper_script(), encoding="ascii", newline="")
    child_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("_MEIPASS", "_PYI", "_MEI"))
    }
    subprocess.Popen(
        [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(helper_path)],
        cwd=str(directory),
        env=child_environment,
        creationflags=0x08000000 | 0x00000200,
        close_fds=True,
    )
    return helper_path


def cleanup_update_files(directory: Path) -> None:
    for name in (
        BACKUP_EXECUTABLE_NAME,
        STAGED_EXECUTABLE_NAME,
        f"{STAGED_EXECUTABLE_NAME}.part",
        UPDATE_HELPER_NAME,
    ):
        try:
            (directory / name).unlink(missing_ok=True)
        except OSError:
            pass
