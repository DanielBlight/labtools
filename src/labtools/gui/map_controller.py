"""Own one map worker and its thread, independently of the window."""

from __future__ import annotations

import traceback
from pathlib import Path
from threading import Event, Lock

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal, pyqtSlot

from labtools.acquisition.intensity_map import IntensityMapConfig, acquire_intensity_map


class MapWorker(QObject):
    """Run blocking intensity-map acquisition outside the Qt main thread."""

    progress = pyqtSignal(object)

    finished = pyqtSignal(object)

    failed = pyqtSignal(str, str)

    def __init__(
        self,
        config: IntensityMapConfig,
        resume_directory: Path | None,
        acquisition=None,
        *,
        progress_callback=None,
    ) -> None:

        super().__init__()

        self.config = config

        self.resume_directory = resume_directory

        self._cancel = Event()
        self._acquisition = acquisition or acquire_intensity_map
        self._progress_callback = progress_callback or self.progress.emit

    @pyqtSlot()
    def run(self) -> None:

        try:
            result = self._acquisition(
                self.config,
                resume_directory=self.resume_directory,
                progress_callback=self._progress_callback,
                cancel_requested=self._cancel.is_set,
            )

        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc), traceback.format_exc())

        else:
            self.finished.emit(result)

    def cancel(self) -> None:

        self._cancel.set()


class MapController(QObject):
    progress = pyqtSignal(object)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str, str)
    idle = pyqtSignal()

    def __init__(self, parent=None, *, acquisition=None):
        super().__init__(parent)
        self.thread = None
        self.worker = None
        self._acquisition = acquisition
        self._progress_lock = Lock()
        self._pending_progress = None
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(100)
        self._progress_timer.timeout.connect(self._flush_progress)

    def _publish_progress(self, snapshot):
        # Called on the acquisition thread: no Qt calls and no per-point events.
        # Snapshots own their arrays; replacing the reference bounds retained work.
        with self._progress_lock:
            self._pending_progress = snapshot

    @pyqtSlot()
    def _flush_progress(self):
        with self._progress_lock:
            snapshot, self._pending_progress = self._pending_progress, None
        if snapshot is not None:
            self.progress.emit(snapshot)

    @pyqtSlot(object)
    def _finished(self, result):
        self._progress_timer.stop()
        self._flush_progress()
        self.finished.emit(result)

    @pyqtSlot(str, str)
    def _failed(self, message, details):
        self._progress_timer.stop()
        self._flush_progress()
        self.failed.emit(message, details)

    @property
    def busy(self):
        return self.thread is not None

    def start(self, config, resume_directory=None):
        if self.busy:
            raise RuntimeError("A map is already running or finishing cleanup")
        config.validate()
        thread = QThread(self)
        with self._progress_lock:
            self._pending_progress = None
        worker = MapWorker(
            config, resume_directory, self._acquisition,
            progress_callback=self._publish_progress,
        )
        self.thread, self.worker = thread, worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._finished)
        worker.failed.connect(self._failed)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._release)
        self._progress_timer.start()
        thread.start()

    def cancel(self):
        if self.worker is not None:
            # A queued slot cannot interrupt a blocking run; Event.set is thread-safe.
            self.worker.cancel()
            self._progress_timer.stop()

    @pyqtSlot()
    def _release(self):
        self._progress_timer.stop()
        thread = self.thread
        self.worker = None
        self.thread = None
        if thread is not None:
            thread.deleteLater()
        self.idle.emit()
