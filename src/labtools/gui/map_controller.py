"""Own one map worker and its thread, independently of the window."""
from __future__ import annotations
from pathlib import Path
from threading import Event
import traceback
from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
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
    ) -> None:

        super().__init__()

        self.config = config

        self.resume_directory = resume_directory

        self._cancel = Event()
        self._acquisition = acquisition or acquire_intensity_map

    @pyqtSlot()
    def run(self) -> None:

        try:
            result = self._acquisition(
                self.config,
                resume_directory=self.resume_directory,
                progress_callback=self.progress.emit,
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

    @property
    def busy(self):
        return self.thread is not None

    def start(self, config, resume_directory=None):
        if self.busy:
            raise RuntimeError("A map is already running or finishing cleanup")
        config.validate()
        thread = QThread(self)
        worker = MapWorker(config, resume_directory, self._acquisition)
        self.thread, self.worker = thread, worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress)
        worker.finished.connect(self.finished)
        worker.failed.connect(self.failed)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._release)
        thread.start()

    def cancel(self):
        if self.worker is not None:
            # A queued slot cannot interrupt a blocking run; Event.set is thread-safe.
            self.worker.cancel()

    @pyqtSlot()
    def _release(self):
        thread = self.thread
        self.worker = None
        self.thread = None
        if thread is not None:
            thread.deleteLater()
        self.idle.emit()
