"""Qt helper for running asynchronous operations outside the UI thread."""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable, Coroutine
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class AsyncTaskRunner(QObject):
    """Run an asynchronous operation and emit its result or traceback."""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        coroutine_factory: Callable[
            [],
            Coroutine[Any, Any, Any],
        ],
    ) -> None:
        """Store a factory that creates a fresh coroutine when run."""
        super().__init__()
        self.coroutine_factory = coroutine_factory

    @pyqtSlot()
    def run(self) -> None:
        """Execute the coroutine and emit either its result or traceback."""
        try:
            result = asyncio.run(
                self.coroutine_factory()
            )

        except Exception:
            self.failed.emit(
                traceback.format_exc()
            )

        else:
            self.finished.emit(result)