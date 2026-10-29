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


def wait_until(app, predicate, timeout=5000):
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: loop.quit() if predicate() else None)
    QTimer.singleShot(timeout, loop.quit)
    timer.start()
    loop.exec()
    timer.stop()
    assert predicate()


def test_window_builds_valid_simulation_request(app):
    window = HyperspectralWindow()
    request = window.build_request()
    assert request.config.backend == "simulation"
    assert request.config.x_points == request.config.y_points == 2
    assert request.output_path is None
    window.close()


def test_controller_runs_public_facade_and_reports_progress(app):
    window = HyperspectralWindow()
    events = []
    window.controller.progress.connect(events.append)
    window.start()
    wait_until(app, lambda: not window.controller.busy)
    assert window.last_measurement.result.status == "complete"
    assert window.last_measurement.provenance.synthetic is True
    assert any(e.phase == "point_completed" for e in events)
    assert "Synthetic=True" in window.summary.text()
    window.close()


def test_controller_rejects_concurrent_start(app):
    async def held(request, **kwargs):
        while not kwargs["cancel_requested"]():
            await asyncio.sleep(0.001)
        return await __import__(
            "labtools.measurements", fromlist=["acquire_hyperspectral_map_async"]
        ).acquire_hyperspectral_map_async(request, cancel_requested=lambda: True)

    controller = HyperspectralController(acquisition=held)
    window = HyperspectralWindow(controller=controller)
    request = window.build_request()
    controller.start(request)
    with pytest.raises(RuntimeError, match="already running"):
        controller.start(request)
    controller.cancel()
    wait_until(app, lambda: not controller.busy)
    window.close()


def test_close_while_busy_requests_cancel_and_refuses_close(app):
    async def held(request, **kwargs):
        while not kwargs["cancel_requested"]():
            await asyncio.sleep(0.001)
        return await __import__(
            "labtools.measurements", fromlist=["acquire_hyperspectral_map_async"]
        ).acquire_hyperspectral_map_async(request, cancel_requested=lambda: True)

    window = HyperspectralWindow(controller=HyperspectralController(acquisition=held))
    window.start()
    assert window.close() is False
    wait_until(app, lambda: not window.controller.busy)
    assert window.close() is True
