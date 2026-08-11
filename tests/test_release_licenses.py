from __future__ import annotations

import importlib.util
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _license_checker():
    path = PROJECT_ROOT / "scripts" / "check_release_licenses.py"
    spec = importlib.util.spec_from_file_location("rlm_release_license_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _checksum_writer():
    path = PROJECT_ROOT / "scripts" / "write_release_checksum.py"
    spec = importlib.util.spec_from_file_location("rlm_release_checksum", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normal_ci_accepts_another_patch_in_the_documented_python_series() -> None:
    checker = _license_checker()
    notices = "The Windows executable contains Python 3.12.13."

    assert checker._python_notice_errors(
        notices,
        running_version="3.12.12",
        exact_runtime=False,
    ) == []


def test_exact_runtime_check_requires_the_build_python_patch() -> None:
    checker = _license_checker()
    notices = "The Windows executable contains Python 3.12.13."

    errors = checker._python_notice_errors(
        notices,
        running_version="3.12.12",
        exact_runtime=True,
    )

    assert errors == [
        "THIRD_PARTY_NOTICES.md does not match the final build Python 3.12.12."
    ]


def test_ci_rejects_an_undocumented_python_series() -> None:
    checker = _license_checker()
    notices = "The Windows executable contains Python 3.12.13."

    errors = checker._python_notice_errors(
        notices,
        running_version="3.13.1",
        exact_runtime=False,
    )

    assert errors == [
        "THIRD_PARTY_NOTICES.md does not cover the validation Python 3.13 series."
    ]


def test_github_actions_reports_the_specific_license_error(
    monkeypatch,
    capsys,
) -> None:
    checker = _license_checker()
    monkeypatch.setitem(os.environ, "GITHUB_ACTIONS", "true")

    checker._report_error("missing 100%\nnotice")

    assert capsys.readouterr().err == (
        "::error title=Release license check::missing 100%25%0Anotice\n"
    )


def test_executable_build_requires_the_exact_runtime_license_check() -> None:
    build_script = (PROJECT_ROOT / "build_exe.bat").read_text(encoding="utf-8")

    assert "check_release_licenses.py\" --final --exact-runtime" in build_script
    assert "PYINSTALLER_CONFIG_DIR=%~dp0..\\..\\build\\PyInstallerCache" in build_script
    assert "scripts\\write_release_checksum.py" in build_script


def test_executable_build_excludes_private_observation_inputs() -> None:
    build_script = (PROJECT_ROOT / "build_exe.bat").read_text(encoding="utf-8")

    assert '--add-data "%~dp0data;data"' not in build_script
    assert "data\\research\\observations" not in build_script
    assert "data\\research\\master.json;data\\research" in build_script
    assert "data\\research\\locales;data\\research\\locales" in build_script


def test_release_checksum_uses_the_stable_executable_name() -> None:
    writer = _checksum_writer()

    assert writer.checksum_line(
        r"nested\RLMResearchPlanner.exe",
        "a" * 64,
    ) == (
        f"{'a' * 64}  RLMResearchPlanner.exe\n"
    )
