"""Exercise real Qt threads with injected acquisition/mirror implementations."""
import time
from threading import Event, get_ident
from types import SimpleNamespace
import pytest

pytest.importorskip('PyQt6.QtCore', exc_type=ImportError)
from PyQt6.QtCore import QCoreApplication, QEvent
from labtools.gui.map_controller import MapController
from labtools.gui.mirror_controller import HardwareThread


@pytest.fixture(scope='module')
def app():
    application = QCoreApplication.instance() or QCoreApplication([])
    yield application


def spin(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() > deadline:
            pytest.fail('Qt lifecycle timed out')
        time.sleep(.001)
    app.processEvents()


@pytest.mark.parametrize('mode', ['success', 'failure', 'cancel'])
def test_map_lifecycle_and_restart(app, mode):
    entered, release = Event(), Event()
    results, failures, progress = [], [], []
    calls = []
    def acquire(config, **kwargs):
        calls.append((get_ident(), kwargs['resume_directory']))
        entered.set()
        release.wait(3)
        kwargs['progress_callback']('point')
        if mode == 'failure':
            raise TimeoutError('injected failure')
        return {'cancelled': kwargs['cancel_requested']()}
    c = MapController(acquisition=acquire)
    c.finished.connect(results.append)
    c.failed.connect(lambda message, detail: failures.append((message, detail)))
    c.progress.connect(progress.append)
    config = SimpleNamespace(validate=lambda: None)
    try:
        c.start(config, 'resume-folder')
        assert c.busy
        spin(app, entered.is_set)
        with pytest.raises(RuntimeError, match='already running'):
            c.start(config)
        if mode == 'cancel': c.cancel()
        release.set()
        spin(app, lambda: not c.busy)
        assert c.worker is None and c.thread is None
        assert calls[0] == (calls[0][0], 'resume-folder')
        assert calls[0][0] != get_ident()
        assert progress == ['point']
        if mode == 'failure':
            assert failures[0][0] == 'injected failure'
            assert 'TimeoutError' in failures[0][1]
        else:
            assert results == [{'cancelled': mode == 'cancel'}]
        c.start(config)
        spin(app, lambda: not c.busy)
        assert len(calls) == 2
    finally:
        release.set()
        c.cancel()
        if c.thread is not None: c.thread.wait(5000)
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_invalid_config_does_not_start_thread(app):
    def invalid(): raise ValueError('bad config')
    c = MapController(acquisition=lambda *a, **k: None)
    with pytest.raises(ValueError): c.start(SimpleNamespace(validate=invalid))
    assert not c.busy and c.worker is None


@pytest.mark.parametrize('failure', [None, 'connect', 'move', 'close'])
def test_mirror_owned_connection_and_fault_shutdown(app, failure):
    calls, done, errors = [], [], []
    class Device:
        def close(self):
            calls.append(('close', get_ident()))
            if failure == 'close': raise OSError('close failed')
    class Mirror:
        def move(self, x, y):
            calls.append(('move', get_ident(), x, y))
            if failure == 'move': raise OSError('move failed')
    def factory():
        calls.append(('connect', get_ident()))
        if failure == 'connect': raise OSError('connect failed')
        return Device(), Mirror()
    worker = HardwareThread(backend_factory=factory)
    worker.done.connect(lambda action, target: done.append((action, target)))
    worker.failed.connect(errors.append)
    worker.start()
    try:
        worker.commands.put_nowait(('connect', None))
        spin(app, lambda: bool(done or errors))
        if failure == 'connect':
            spin(app, lambda: not worker.isRunning())
            assert [x[0] for x in calls] == ['connect']
            return
        assert [x[0] for x in calls] == ['connect']  # no implicit move/home
        worker.commands.put_nowait(('move', (1., -2.)))
        spin(app, lambda: len(done) == 2 or bool(errors))
        if failure != 'move':
            worker.commands.put_nowait(('quit', None))
        spin(app, lambda: not worker.isRunning())
        assert [x[0] for x in calls] == ['connect', 'move', 'close']
        assert all(x[1] != get_ident() for x in calls)
        assert bool(errors) == (failure is not None)
    finally:
        if worker.isRunning():
            worker.commands.put(('quit', None), timeout=2)
        assert worker.wait(5000)
        app.processEvents()
