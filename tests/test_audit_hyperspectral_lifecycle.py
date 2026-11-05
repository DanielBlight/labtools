"""Bounded QtCore lifecycle regressions; no widgets or physical devices."""
from __future__ import annotations

import asyncio
from threading import Event

import pytest

pytest.importorskip("PyQt6.QtCore")
from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer

from labtools.gui.hyperspectral_controller import HyperspectralController


class Request:
    def validate(self):
        pass


@pytest.fixture(scope="module")
def app():
    existing = QCoreApplication.instance()
    if existing is not None:
        return existing
    # Use QApplication when available so later widget tests can share the instance.
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        return QCoreApplication([])
    return QApplication([])


def wait_for(predicate, timeout_ms=3000):
    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(5)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(timeout_ms)
    loop.exec()
    poll.stop()
    deadline.stop()
    assert predicate(), "Bounded Qt event-loop deadline expired"


def observe(controller):
    events = []
    controller.failed.connect(lambda *args: events.append(("failed", args)))
    controller.finished.connect(lambda value: events.append(("finished", value)))
    controller.idle.connect(lambda: events.append(("idle", None)))
    return events


@pytest.mark.parametrize("kind", [RuntimeError, asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_repeated_failures_emit_exactly_one_terminal_then_idle(app, kind):
    async def acquisition(*args, **kwargs):
        raise kind()

    controller = HyperspectralController(acquisition=acquisition)
    events = observe(controller)
    for _ in range(3):
        events.clear()
        controller.start(Request())
        wait_for(lambda: not controller.busy)
        assert [name for name, _ in events] == ["failed", "idle"]
        assert events[0][1][0] == kind.__name__
        assert kind.__name__ in events[0][1][1]
        assert controller.worker is None
        assert controller.thread is None


def test_immediate_cancel_reaches_acquisition_and_idle(app):
    entered = Event()

    async def acquisition(*args, **kwargs):
        entered.set()
        while not kwargs["cancel_requested"]():
            await asyncio.sleep(0.001)
        raise asyncio.CancelledError()

    controller = HyperspectralController(acquisition=acquisition)
    events = observe(controller)
    controller.start(Request())
    controller.cancel()
    controller.cancel()
    wait_for(lambda: not controller.busy)
    assert entered.is_set()
    assert [name for name, _ in events] == ["failed", "idle"]


def test_busy_reservation_survives_delayed_cleanup(app):
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
    events = observe(controller)
    controller.start(Request())
    controller.cancel()
    try:
        wait_for(cleanup_started.is_set)
        assert controller.busy
        assert events == []
        with pytest.raises(RuntimeError, match="already running"):
            controller.start(Request())
        controller.cancel()
    finally:
        release.set()
        wait_for(lambda: not controller.busy)
    assert [name for name, _ in events] == ["failed", "idle"]


def test_borrowed_runtime_forwarded_without_controller_close(app):
    class Runtime:
        closed = 0

        def close(self):
            self.closed += 1

    runtime = Runtime()
    received = []

    async def acquisition(*args, **kwargs):
        received.append(kwargs["runtime"])
        return "result"

    controller = HyperspectralController(acquisition=acquisition)
    events = observe(controller)
    for _ in range(3):
        events.clear()
        controller.start(Request(), runtime=runtime)
        wait_for(lambda: not controller.busy)
        assert [name for name, _ in events] == ["finished", "idle"]
    assert received == [runtime] * 3
    assert runtime.closed == 0
