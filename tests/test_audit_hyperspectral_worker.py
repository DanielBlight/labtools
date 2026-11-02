"""Qt-only worker and dark-selection regressions; no hardware."""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from labtools.gui.hyperspectral_controller import HyperspectralController
from labtools.gui.hyperspectral_gui import HyperspectralWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("error", [asyncio.CancelledError(), KeyboardInterrupt(), SystemExit()])
def test_worker_control_exception_reports_failure_and_reaches_idle(app, error):
    async def acquisition(*args, **kwargs):
        raise error

    controller = HyperspectralController(acquisition=acquisition)
    window = HyperspectralWindow(controller=controller)
    failures = []
    controller.failed.connect(lambda *args: failures.append(args))
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    controller.idle.connect(loop.quit)
    controller.start(window.build_request())
    timer.start(5000)
    loop.exec()
    timer.stop()
    assert not controller.busy
    assert len(failures) == 1
    assert failures[0][0] == type(error).__name__
    window.close()


def test_cached_dark_not_forwarded_for_none_mode(app):
    window = HyperspectralWindow()
    window.dark_record = object()
    window.dark_mode.setCurrentText("none")
    assert window.build_request().dark is None
    window.close()
