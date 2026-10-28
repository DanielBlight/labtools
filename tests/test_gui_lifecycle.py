"""Window lifecycle tests run in isolated processes with fake hardware only."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)

SCRIPT = r"""
import sys, time
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QSettings
app = QApplication([])
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, sys.argv[2])
QMessageBox.warning = lambda *a, **k: QMessageBox.StandardButton.Ok
QMessageBox.critical = lambda *a, **k: QMessageBox.StandardButton.Ok
QMessageBox.exec = lambda *a, **k: QMessageBox.StandardButton.Ok
mode = sys.argv[1]
def spin(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, 'Window lifecycle timed out'
        time.sleep(.001)
    app.processEvents()
entered, release = Event(), Event()
if mode.startswith('map'):
    from labtools.gui.intensity_map_gui import IntensityMapWindow
    from labtools.acquisition.intensity_map import IntensityMapConfig
    def acquire(config, **kw):
        entered.set()
        assert release.wait(3)
        if mode == 'map-failure': raise TimeoutError('fake timeout')
        return SimpleNamespace(complete=not kw['cancel_requested'](), output_directory=Path(sys.argv[2]))
    w = IntensityMapWindow(acquisition=acquire)
    w.simulation_mode.setChecked(True)
    config = IntensityMapConfig(
        x_start_v=-1., x_stop_v=1., x_points=2,
        y_start_v=-1., y_stop_v=1., y_points=2,
        channels=(1,), channel_thresholds_v=(.1,), channel_edges=('rising',),
        integration_time_s=.01, settle_time_s=0., output_root=Path(sys.argv[2]),
        backend='simulation', save_results=False,
    )
    w.show()
    try:
        w._start_worker(config)
        spin(entered.is_set)
        assert not w.start_button.isEnabled()
        assert not w.simulation_mode.isEnabled()
        assert not w.close(), 'Must not close while worker is owned'
        if mode == 'map-stop': w.request_stop()
        release.set()
        spin(lambda: not w.map_controller.busy)
        assert w.start_button.isEnabled() and w.resume_button.isEnabled()
        assert not w.stop_button.isEnabled()
        assert w.simulation_mode.isEnabled()
        assert w._thread is None and w._worker is None
        w._start_worker(config)
        spin(lambda: not w.map_controller.busy)
        assert w.close()
    finally:
        release.set()
        w.map_controller.cancel()
        if w._thread is not None: w._thread.wait(5000)
        app.processEvents()
        w.close()
else:
    from labtools.gui.mirror_voltage_gui import MirrorWindow
    calls = []
    class Device:
        def close(self): calls.append('close')
    class Mirror:
        def move(self, x, y):
            calls.append('move')
            entered.set()
            assert release.wait(3)
            if mode == 'mirror-failure': raise OSError('fake move failure')
    def factory():
        calls.append('connect')
        return Device(), Mirror()
    w = MirrorWindow(backend_factory=factory)
    w.show()
    try:
        w.toggle_connection()
        spin(lambda: w.connected and not w.busy)
        assert calls == ['connect']
        w.move_target()
        spin(entered.is_set)
        assert not w.close(), 'Busy move must not close the worker'
        release.set()
        spin(lambda: not w.busy)
        if mode == 'mirror-failure':
            spin(lambda: not w.worker.isRunning())
            assert w.fault and not w.connected
        else:
            assert w.connected
        w.close()
        spin(lambda: not w.worker.isRunning())
        app.processEvents()
        w.close()
        assert calls == ['connect', 'move', 'close']
    finally:
        release.set()
        if w.worker.isRunning():
            w.worker.commands.put(('quit', None), timeout=3)
        assert w.worker.wait(5000)
        app.processEvents()
        w.close()
"""


@pytest.mark.parametrize(
    "mode",
    ["map-success", "map-stop", "map-failure", "mirror-success", "mirror-failure"],
)
def test_window_lifecycle(mode, tmp_path):
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        MPLBACKEND="Agg",
        XDG_CONFIG_HOME=str(tmp_path),
        PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
    )
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, mode, str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
