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


@pytest.mark.parametrize("mode", ["none", "fresh", "pre_taken"])
def test_dark_mode_round_trip_preserves_cache(app, mode):
    import numpy as np

    from labtools.acquisition.spectrum_service import DarkRecord

    window = HyperspectralWindow()
    settings = window.build_request().config.spectrum
    dark = DarkRecord(
        settings, np.array([500.0, 600.0]), np.array([1.0, 2.0]),
        "audit-dark", "2026-11-02T12:16:04+00:00",
    )
    window.dark_record = dark
    try:
        for selected in ("pre_taken", "none", "fresh", mode):
            window.dark_mode.setCurrentText(selected)
            request = window.build_request()
            assert request.dark is (dark if selected == "pre_taken" else None)
            assert window.dark_record is dark
    finally:
        window.close()


def test_close_during_cleanup_waits_and_rejects_restart(app):
    from threading import Event

    from labtools.gui.hyperspectral_controller import HyperspectralController

    cleanup_started = Event()
    release = Event()

    async def acquisition(*args, **kwargs):
        try:
            while not kwargs["cancel_requested"]():
                await asyncio.sleep(0.001)
            raise asyncio.CancelledError()
        finally:
            cleanup_started.set()
            while not release.is_set():
                await asyncio.sleep(0.001)

    controller = HyperspectralController(acquisition=acquisition)
    window = HyperspectralWindow(controller=controller)
    failures, idles = [], []
    controller.failed.connect(lambda *args: failures.append(args))
    controller.idle.connect(lambda: idles.append(True))
    window.show()
    window.start()
    try:
        assert window.close() is False
        # Local timers bound the wait without blocking the GUI event loop.
        loop = QEventLoop()
        poll = QTimer()
        poll.setInterval(5)
        poll.timeout.connect(lambda: loop.quit() if cleanup_started.is_set() else None)
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        poll.start()
        deadline.start(3000)
        loop.exec()
        poll.stop()
        deadline.stop()
        assert cleanup_started.is_set()
        assert controller.busy
        assert window.isVisible()
        assert window.close() is False
        with pytest.raises(RuntimeError, match="already running"):
            controller.start(window.build_request())
    finally:
        release.set()
        loop = QEventLoop()
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        controller.idle.connect(loop.quit)
        deadline.start(3000)
        if controller.busy:
            loop.exec()
        deadline.stop()
        assert not controller.busy
        window.close()
    assert len(failures) == len(idles) == 1
    assert not window.isVisible()
