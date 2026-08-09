from __future__ import annotations

import re

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from rlm_research_planner.services import updater
from rlm_research_planner.ui.update_worker import (
    UpdateCheckWorker,
    UpdateDownloadWorker,
)
from rlm_research_planner.ui.visual_styles import apply_dialog_visual_style


class UpdateController(QObject):
    def __init__(self, window, settings_repository, app_settings) -> None:
        super().__init__(window)
        self.window = window
        self.settings_repository = settings_repository
        self.app_settings = app_settings
        self._check_worker: UpdateCheckWorker | None = None
        self._download_worker: UpdateDownloadWorker | None = None
        self._progress_dialog: QProgressDialog | None = None
        self._check_button = None
        self._status_label = None
        self._startup_checkbox = None
        if updater.distribution_type() != "source":
            updater.cleanup_update_files(updater.install_directory())

    def t(self, key: str, **values: object) -> str:
        return self.window.t(key, **values)

    def _style_dialog(self, dialog):
        apply_dialog_visual_style(dialog, self.app_settings.visual_style)
        return dialog

    def _message_box(
        self,
        icon: QMessageBox.Icon,
        message: str,
        *,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton | None = None,
    ) -> QMessageBox:
        box = QMessageBox(self.window)
        box.setWindowTitle(self.t("update.dialog.title"))
        box.setIcon(icon)
        box.setText(message)
        box.setStandardButtons(buttons)
        if default_button is not None:
            box.setDefaultButton(default_button)
        return self._style_dialog(box)

    def _show_information(self, message: str) -> None:
        self._message_box(QMessageBox.Icon.Information, message).exec()

    def _show_warning(self, message: str) -> None:
        self._message_box(QMessageBox.Icon.Warning, message).exec()

    def bind_help_controls(self, check_button, status_label, startup_checkbox) -> None:
        self._check_button = check_button
        self._status_label = status_label
        self._startup_checkbox = startup_checkbox
        check_button.clicked.connect(lambda: self.start_check(manual=True))
        startup_checkbox.setChecked(self.app_settings.update_check_on_startup)
        startup_checkbox.toggled.connect(self._set_startup_check)
        if updater.update_checks_enabled():
            check_button.setEnabled(True)
            status_label.setVisible(True)
            status_label.setText(self.t("update.status.ready"))
        else:
            check_button.setEnabled(False)
            status_label.clear()
            status_label.setVisible(False)

    def schedule_startup_check(self) -> None:
        if (
            self.app_settings.update_check_on_startup
            and updater.update_checks_enabled()
        ):
            QTimer.singleShot(1200, lambda: self.start_check(manual=False))

    def _set_startup_check(self, enabled: bool) -> None:
        self.app_settings.update_check_on_startup = bool(enabled)
        self.settings_repository.save(self.app_settings)

    def start_check(self, *, manual: bool) -> None:
        if not updater.update_checks_enabled():
            return
        if self._check_worker is not None and self._check_worker.isRunning():
            return
        if self._check_button is not None:
            self._check_button.setEnabled(False)
        if self._status_label is not None:
            self._status_label.setText(self.t("update.status.checking"))
        worker = UpdateCheckWorker(self)
        worker.succeeded.connect(
            lambda release, requested=manual: self._check_finished(
                release, manual=requested
            )
        )
        worker.failed.connect(
            lambda message, requested=manual: self._check_failed(
                message, manual=requested
            )
        )
        worker.finished.connect(lambda current=worker: self._check_worker_done(current))
        self._check_worker = worker
        worker.start()

    def _check_worker_done(self, worker: UpdateCheckWorker) -> None:
        if self._check_worker is worker:
            self._check_worker = None
        worker.deleteLater()
        if self._check_button is not None and updater.update_checks_enabled():
            self._check_button.setEnabled(True)

    def _check_finished(self, release, *, manual: bool) -> None:
        if release is None:
            if self._status_label is not None:
                self._status_label.setText(self.t("update.status.latest"))
            if manual:
                self._show_information(self.t("update.latest"))
            return
        if self._status_label is not None:
            self._status_label.setText(
                self.t("update.status.available", version=release.version)
            )
        if (
            not manual
            and self.app_settings.update_skipped_version == release.version
        ):
            return
        self._show_available_release(release)

    def _check_failed(self, message: str, *, manual: bool) -> None:
        if self._status_label is not None:
            self._status_label.setText(self.t("update.status.error"))
        if manual:
            self._show_warning(self.t("update.check_failed", error=message))

    @staticmethod
    def _plain_release_notes(markdown: str, maximum: int = 500) -> str:
        lines: list[str] = []
        for line in markdown.splitlines():
            text = re.sub(r"^\s*#{1,6}\s*", "", line.rstrip())
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
            text = re.sub(r"`(.+?)`", r"\1", text)
            text = re.sub(r"^\s*[-*+]\s+", "・", text)
            lines.append(text)
        result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        if len(result) > maximum:
            return result[:maximum].rstrip() + "…"
        return result

    def _show_available_release(self, release) -> None:
        unavailable_reason = updater.auto_update_unavailable_reason(release)
        notes = self._plain_release_notes(release.body)
        message = self.t("update.available", version=release.version)
        if notes:
            message += f"\n\n{self.t('update.release_notes')}\n{notes}"
        if unavailable_reason:
            message += f"\n\n{self.t('update.manual_only')}"
        else:
            message += f"\n\n{self.t('update.confirm')}"

        box = QMessageBox(self.window)
        box.setWindowTitle(self.t("update.dialog.title"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(message)
        if unavailable_reason:
            primary = box.addButton(
                self.t("update.open_releases"), QMessageBox.ButtonRole.AcceptRole
            )
        else:
            primary = box.addButton(
                self.t("update.install"), QMessageBox.ButtonRole.AcceptRole
            )
        skip = box.addButton(
            self.t("update.skip"), QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(self.t("update.later"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(primary)
        self._style_dialog(box)
        box.exec()
        clicked = box.clickedButton()
        if clicked is primary:
            if unavailable_reason:
                self.open_releases_page(release.html_url)
            else:
                self._start_download(release)
        elif clicked is skip:
            self.app_settings.update_skipped_version = release.version
            self.settings_repository.save(self.app_settings)
            if self._status_label is not None:
                self._status_label.setText(
                    self.t("update.status.skipped", version=release.version)
                )

    def _start_download(self, release) -> None:
        directory = updater.install_directory()
        if not updater.has_write_permission(directory):
            self._show_warning(
                self.t("update.no_write_permission", path=str(directory))
            )
            return
        if self._download_worker is not None and self._download_worker.isRunning():
            return
        executable = release.asset(updater.APP_EXECUTABLE_NAME)
        total = executable.size if executable is not None and executable.size else 0
        progress = QProgressDialog(
            self.t("update.downloading"),
            self.t("common.cancel"),
            0,
            total,
            self.window,
        )
        progress.setWindowTitle(self.t("update.dialog.title"))
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        self._style_dialog(progress)
        worker = UpdateDownloadWorker(release, directory, self)
        worker.progress.connect(self._download_progress)
        worker.succeeded.connect(
            lambda _path, selected=release: self._download_finished(selected)
        )
        worker.failed.connect(self._download_failed)
        worker.cancelled.connect(self._download_cancelled)
        worker.finished.connect(
            lambda current=worker: self._download_worker_done(current)
        )
        progress.canceled.connect(worker.cancel)
        self._progress_dialog = progress
        self._download_worker = worker
        worker.start()
        progress.show()

    def _download_progress(self, downloaded: int, total: int | None) -> None:
        if self._progress_dialog is None:
            return
        if total:
            self._progress_dialog.setMaximum(total)
            self._progress_dialog.setValue(downloaded)
            self._progress_dialog.setLabelText(
                self.t(
                    "update.download_progress",
                    downloaded=f"{downloaded / 1024 / 1024:.1f}",
                    total=f"{total / 1024 / 1024:.1f}",
                )
            )
        else:
            self._progress_dialog.setRange(0, 0)

    def _close_progress(self) -> None:
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None

    def _download_finished(self, release) -> None:
        self._close_progress()
        box = self._message_box(
            QMessageBox.Icon.Question,
            self.t("update.restart_confirm", version=release.version),
            buttons=(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ),
            default_button=QMessageBox.StandardButton.Yes,
        )
        box.exec()
        clicked_button = box.clickedButton()
        result = (
            box.standardButton(clicked_button)
            if clicked_button is not None
            else QMessageBox.StandardButton.NoButton
        )
        if result != QMessageBox.StandardButton.Yes:
            (updater.install_directory() / updater.STAGED_EXECUTABLE_NAME).unlink(
                missing_ok=True
            )
            return
        try:
            updater.launch_update_helper(updater.install_directory())
        except Exception as error:
            self._show_warning(
                self.t(
                    "update.apply_failed",
                    error=f"{type(error).__name__}: {error}",
                )
            )
            return
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def _download_failed(self, message: str) -> None:
        self._close_progress()
        self._show_warning(self.t("update.download_failed", error=message))

    def _download_cancelled(self) -> None:
        self._close_progress()

    def _download_worker_done(self, worker: UpdateDownloadWorker) -> None:
        if self._download_worker is worker:
            self._download_worker = None
        worker.deleteLater()

    def open_releases_page(self, url: str = "") -> None:
        QDesktopServices.openUrl(QUrl(url or updater.RELEASES_URL))

    def shutdown(self) -> None:
        if self._download_worker is not None and self._download_worker.isRunning():
            self._download_worker.cancel()
            self._download_worker.wait(2000)
        if self._check_worker is not None and self._check_worker.isRunning():
            self._check_worker.requestInterruption()
            self._check_worker.wait(2000)
