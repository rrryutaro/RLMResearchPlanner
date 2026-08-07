from __future__ import annotations

from threading import Event

from PySide6.QtCore import QThread, Signal

from rlm_research_planner.services import updater


class UpdateCheckWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.succeeded.emit(updater.check_for_update(timeout=10))
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")


class UpdateDownloadWorker(QThread):
    progress = Signal(int, object)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, release, directory, parent=None) -> None:
        super().__init__(parent)
        self._release = release
        self._directory = directory
        self._cancel_event = Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            path = updater.stage_update(
                self._release,
                self._directory,
                progress_callback=lambda downloaded, total: self.progress.emit(
                    downloaded, total
                ),
                cancel_event=self._cancel_event,
            )
        except updater.UpdateCancelledError:
            self.cancelled.emit()
            return
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
            return
        self.succeeded.emit(path)
