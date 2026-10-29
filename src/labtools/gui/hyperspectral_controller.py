"""Qt worker/controller for the public hyperspectral facade only."""

from __future__ import annotations

import asyncio
import traceback
from threading import Event

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from labtools.measurements import acquire_hyperspectral_map_async


class HyperspectralWorker(QObject):
    progress = pyqtSignal(object)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str, str)

    def __init__(self, request, runtime=None, acquisition=None) -> None:
        super().__init__()
        self.request = request
        self.runtime = runtime
        self._acquisition = acquisition or acquire_hyperspectral_map_async
        self._cancel = Event()

    @pyqtSlot()
    def run(self) -> None:
        async def acquire():
            return await self._acquisition(
                self.request,
                runtime=self.runtime,
                progress=self.progress.emit,
                cancel_requested=self._cancel.is_set,
            )

        try:
            result = asyncio.run(acquire())
        except Exception as exc:  # noqa: BLE001 - Qt error boundary
            self.failed.emit(str(exc), traceback.format_exc())
        else:
            self.finished.emit(result)

    def cancel(self) -> None:
        self._cancel.set()


class HyperspectralController(QObject):
    progress = pyqtSignal(object)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str, str)
    idle = pyqtSignal()

    def __init__(self, parent=None, *, acquisition=None) -> None:
        super().__init__(parent)
        self.thread = None
        self.worker = None
        self._acquisition = acquisition

    @property
    def busy(self) -> bool:
        return self.thread is not None

    def start(self, request, runtime=None) -> None:
        if self.busy:
            raise RuntimeError("A hyperspectral acquisition is already running")
        request.validate()
        thread = QThread()
        worker = HyperspectralWorker(request, runtime, self._acquisition)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress)
        worker.finished.connect(self.finished)
        worker.failed.connect(self.failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear)
        self.thread, self.worker = thread, worker
        thread.start()

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()

    @pyqtSlot()
    def _clear(self) -> None:
        self.thread = None
        self.worker = None
        self.idle.emit()
