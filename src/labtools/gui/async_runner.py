"""Small Qt helper for running async coroutines off the UI thread."""

from __future__ import annotations

import asyncio
from typing import Callable, Coroutine

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class AsyncTaskRunner(QObject):
    """Run an async coroutine in a worker thread and forward the result to the UI thread.

    Intended to be moved to a :class:`~PyQt6.QtCore.QThread` via
    :meth:`QObject.moveToThread`, then started with ``thread.started.connect(runner.run)``.
    """

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, coroutine_factory: Callable[[], Coroutine]):
        super().__init__()
        self.coroutine_factory = coroutine_factory

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = asyncio.run(self.coroutine_factory())
        except Exception as exc:  # pragma: no cover - UI path only
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)
