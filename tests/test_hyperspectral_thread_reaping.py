"""Do not release wrappers or announce idle before a nonblocking native join."""

import asyncio
import gc
import time

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from labtools.gui.hyperspectral_controller import HyperspectralController


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Request:
    def validate(self):
        pass


def wait_for(predicate, milliseconds=3000):
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(2)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(milliseconds)
    if not predicate():
        loop.exec()
    poll.stop()
    deadline.stop()
    assert predicate(), "Bounded teardown deadline expired"


def test_finished_is_not_yet_joined_keeps_references_and_busy(app):
    controller = HyperspectralController()
    events = []
    controller.idle.connect(lambda: events.append('idle'))
    class NativeThread:
        ready = False
        deleted = False
        def wait(self, timeout):
            assert timeout == 0
            return self.ready
        def deleteLater(self):
            self.deleted = True
    thread = NativeThread()
    worker = object()
    controller.thread, controller.worker = thread, worker
    start = time.monotonic()
    controller._clear()
    assert time.monotonic() - start < .5
    assert controller.busy and controller.worker is worker
    assert controller.thread is thread and not thread.deleted and not events
    assert controller._reap_timer.isActive()
    with pytest.raises(RuntimeError, match='already running'):
        controller.start(Request())
    thread.ready = True
    wait_for(lambda: not controller.busy)
    assert controller.worker is None and thread.deleted
    assert events == ['idle'] and not controller._reap_timer.isActive()
    controller._clear()
    assert events == ['idle']


@pytest.mark.parametrize('error_type', [None, RuntimeError, asyncio.CancelledError, KeyboardInterrupt, SystemExit])
def test_repeated_terminal_cleanup_joined_before_idle_and_restart(app, error_type):
    async def acquisition(*args, **kwargs):
        if error_type is not None:
            raise error_type('intentional test terminal')
        return 'result'
    controller = HyperspectralController(acquisition=acquisition)
    events = []
    controller.finished.connect(lambda value: events.append('finished'))
    controller.failed.connect(lambda *args: events.append('failed'))
    threads = []
    def idle():
        assert controller.thread is None and controller.worker is None
        assert threads[-1].wait(0)
        events.append('idle')
    controller.idle.connect(idle)
    for _ in range(20):
        events.clear()
        controller.start(Request())
        thread = controller.thread
        assert thread.parent() is controller
        threads.append(thread)
        wait_for(lambda: not controller.busy)
        assert events == ['failed' if error_type else 'finished', 'idle']
        threads.clear()
        gc.collect()
