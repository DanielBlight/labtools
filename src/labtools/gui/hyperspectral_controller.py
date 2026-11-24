"""Qt worker/controller for the public hyperspectral facade only."""

from __future__ import annotations

import asyncio
import traceback
from threading import Event

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

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
        except BaseException as exc:  # noqa: BLE001 - terminal Qt worker boundary
            # Cancellation and process-control exceptions must not strand QThread.
            self.failed.emit(str(exc) or type(exc).__name__, traceback.format_exc())
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
        self._reap_timer = QTimer(self)
        self._reap_timer.setInterval(5)
        self._reap_timer.timeout.connect(self._clear)

    @property
    def busy(self) -> bool:
        return self.thread is not None

    def start(self, request, runtime=None) -> None:
        if self.busy:
            raise RuntimeError("A hyperspectral acquisition is already running")
        request.validate()
        # Keep C++ ownership as well as Python references until native teardown
        # has joined. QThread.finished precedes thread-local/deferred cleanup.
        thread = QThread(self)
        worker = HyperspectralWorker(request, runtime, self._acquisition)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress)
        worker.finished.connect(self.finished)
        worker.failed.connect(self.failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._clear)
        self.thread, self.worker = thread, worker
        thread.start()

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()

    @pyqtSlot()
    def _clear(self) -> None:
        thread = self.thread
        if thread is None:
            self._reap_timer.stop()
            return
        # Never destroy the last wrapper or block the GUI while native/Python
        # teardown may still need the GIL. A zero-time join is a readiness probe,
        # not a deadline extension or a forced interruption of acquisition.
        if not thread.wait(0):
            self._reap_timer.start()
            return
        self._reap_timer.stop()
        self.worker = None
        self.thread = None
        thread.deleteLater()
        self.idle.emit()
