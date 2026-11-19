"""Bound GUI progress work without changing acquisition or cancellation."""

import time
from threading import Event, get_ident
from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6.QtCore", exc_type=ImportError)
from PyQt6.QtCore import QCoreApplication, QTimer

from labtools.gui.map_controller import MapController


@pytest.mark.parametrize("failure", [False, True])
def test_burst_is_coalesced_and_final_progress_precedes_terminal(failure):
    app = QCoreApplication.instance() or QCoreApplication([])
    ready, release = Event(), Event()
    events, threads = [], []

    def acquire(config, **kwargs):
        for i in range(20000):
            kwargs["progress_callback"](i)
        ready.set()
        assert release.wait(5)
        if failure:
            raise ValueError("injected")
        return "result"

    controller = MapController(acquisition=acquire)
    controller.progress.connect(lambda value: (events.append(("progress", value)), threads.append(get_ident())))
    controller.finished.connect(lambda value: events.append(("finished", value)))
    controller.failed.connect(lambda *args: events.append(("failed", args[0])))
    controller.idle.connect(lambda: events.append(("idle", None)))
    try:
        controller.start(SimpleNamespace(validate=lambda: None))
        assert ready.wait(5)  # Deliberately do not service GUI events during burst.
        assert events == []
        assert controller._pending_progress == 19999
        release.set()
        end = time.monotonic() + 5
        while controller.busy and time.monotonic() < end:
            app.processEvents()
            time.sleep(.001)
        assert not controller.busy
        assert events[0] == ("progress", 19999)
        assert len([e for e in events if e[0] == "progress"]) == 1
        assert events[1][0] == ("failed" if failure else "finished")
        assert events[-1][0] == "idle"
        assert threads == [get_ident()]
        assert controller._pending_progress is None
        assert not controller._progress_timer.isActive()
    finally:
        release.set()
        controller.cancel()
        if controller.thread is not None:
            controller.thread.wait(5000)
        app.processEvents()


def test_timer_cancel_survives_fast_producer_slow_display_and_restart():
    app = QCoreApplication.instance() or QCoreApplication([])
    results, rendered, heartbeat = [], [], []
    calls = []

    def acquire(config, **kwargs):
        calls.append(get_ident())
        i = 0
        while not kwargs["cancel_requested"]():
            kwargs["progress_callback"](i)
            i += 1
            time.sleep(.0001)
        return i

    controller = MapController(acquisition=acquire)

    def slow_display(value):
        rendered.append(value)
        time.sleep(.025)

    controller.progress.connect(slow_display)
    controller.finished.connect(results.append)
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: heartbeat.append(time.monotonic()))
    timer.start()
    try:
        for _ in range(2):
            controller.start(SimpleNamespace(validate=lambda: None))
            QTimer.singleShot(250, controller.cancel)
            end = time.monotonic() + 3
            while controller.busy and time.monotonic() < end:
                app.processEvents()
                time.sleep(.001)
            assert not controller.busy
            assert controller._pending_progress is None
        assert len(results) == 2 and all(value > 0 for value in results)
        assert len(rendered) < 15
        assert len(heartbeat) >= 5
        assert all(thread != get_ident() for thread in calls)
    finally:
        timer.stop()
        controller.cancel()
        if controller.thread is not None:
            controller.thread.wait(5000)
        app.processEvents()
