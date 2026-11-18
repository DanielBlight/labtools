"""Unified offline navigation/lifecycle contracts; no native devices."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from labtools.simulation.workspace import (
    busy_workflows,
    close_workflows,
    stop_workflows,
)

ROOT = Path(__file__).resolve().parents[1]


def pages(map_busy=False, spectrum_busy=False, teardown=False):
    events = []
    mapping = SimpleNamespace(
        map_controller=SimpleNamespace(busy=map_busy),
        request_stop=lambda: events.append("map stop"),
        close=lambda: events.append("map close") or True,
        show=lambda: events.append("map show"),
    )
    spectrum = SimpleNamespace(
        _spectrometer_busy=spectrum_busy, _async_tasks=[object()] if teardown else [],
        request_stop=lambda: events.append("spectrum stop"),
        close=lambda: events.append("spectrum close") or True,
        show=lambda: events.append("spectrum show"),
    )
    return {"Intensity map": mapping, "Spectrum": spectrum}, events


@pytest.mark.parametrize(
    "map_busy,spectrum_busy,teardown,expected",
    [(False, False, False, ()), (True, False, False, ("Intensity map",)),
     (False, True, False, ("Spectrum",)), (False, False, True, ("Spectrum",)),
     (True, True, True, ("Intensity map", "Spectrum"))],
)
def test_busy_includes_worker_teardown(map_busy, spectrum_busy, teardown, expected):
    panels, _ = pages(map_busy, spectrum_busy, teardown)
    assert busy_workflows(panels) == expected


def test_global_stop_reaches_all_active_workflows():
    panels, events = pages(True, True)
    assert stop_workflows(panels) == ()
    assert events == ["map stop", "spectrum stop"]


def test_stop_failure_does_not_prevent_other_stop():
    panels, events = pages(True, True)

    def fail():
        raise RuntimeError("stop failed")

    panels["Intensity map"].request_stop = fail
    assert stop_workflows(panels) == ("Intensity map: RuntimeError: stop failed",)
    assert events == ["spectrum stop"]


def test_idle_stop_does_not_touch_panels():
    panels, events = pages()
    assert stop_workflows(panels) == ()
    assert not events


def test_close_refused_until_all_workers_idle():
    panels, events = pages(teardown=True)
    assert not close_workflows(panels)
    assert not events
    panels["Spectrum"]._async_tasks.clear()
    assert close_workflows(panels)
    assert events == ["map close", "spectrum close"]


def test_child_close_veto_restores_hidden_panels():
    panels, events = pages()
    panels["Spectrum"].close = lambda: False
    assert not close_workflows(panels)
    assert events == ["map close", "map show", "spectrum show"]


def test_unknown_workflow_is_not_silently_ignored():
    with pytest.raises(ValueError, match="Unknown workspace workflow"):
        busy_workflows({"unknown": object()})


def test_cli_routes_to_one_simulation_workspace(monkeypatch, tmp_path):
    from labtools.cli import main

    created = []

    class App:
        def __init__(self, args):
            pass

        def exec(self):
            return 0

    class Window:
        def __init__(self, **kwargs):
            created.append(kwargs)

        def show(self):
            created.append("shown")

    qt = ModuleType("PyQt6")
    qt.__path__ = []
    widgets = ModuleType("PyQt6.QtWidgets")
    widgets.QApplication = App
    workspace = ModuleType("labtools.gui.workspace")
    workspace.SimulationWorkspace = Window
    for name, module in {"PyQt6": qt, "PyQt6.QtWidgets": widgets, "labtools.gui.workspace": workspace}.items():
        monkeypatch.setitem(sys.modules, name, module)
    with pytest.raises(SystemExit) as caught:
        main(["simulate", "workspace", "--output", str(tmp_path)])
    assert caught.value.code == 0
    assert created == [{"output_root": tmp_path}, "shown"]


def test_actual_workspace_switch_acquire_stop_and_close(tmp_path):
    if importlib.util.find_spec("PyQt6") is None:
        pytest.skip("PyQt6 unavailable: actual unified window remains unassessed")
    code = r'''
import builtins, sys, time
from pathlib import Path
original = builtins.__import__
def guarded(name, *args, **kwargs):
    blocked=("labtools.devices", "horiba_sdk", "u6", "pyvisa", "serial")
    if any(name==prefix or name.startswith(prefix+".") for prefix in blocked):
        raise AssertionError("Native import forbidden: "+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from PyQt6.QtWidgets import QApplication
from labtools.gui.workspace import SimulationWorkspace
from labtools.simulation.workspace import busy_workflows
app=QApplication([])
w=SimulationWorkspace(output_root=Path(sys.argv[1])); w.show()
m=w.pages["Intensity map"]; s=w.pages["Spectrum"]
errors=[]
s._show_error=lambda *a: errors.append(a)
m.map_controller.failed.connect(lambda *a: errors.append(a))
def wait(predicate, timeout=20):
    end=time.monotonic()+timeout
    while not predicate():
        app.processEvents(); time.sleep(.005)
        assert time.monotonic()<end,"Unified workflow timed out"
    app.processEvents()
try:
    assert w.tabs.count()==2 and not m.isWindow() and not s.isWindow()
    assert m.simulation_mode.isChecked() and not m.simulation_mode.isEnabled()
    assert not m.laser_group.isEnabled() and not s.laser_group.isEnabled()
    m.integration.setValue(.02); m.settle.setValue(0); m.save_results.setChecked(True)
    m.start_new(); wait(lambda:not m.map_controller.busy)
    assert not errors and m.progress.value()==100
    w.tabs.setCurrentIndex(1)
    s.save_csv.setChecked(True); s.save_png.setChecked(True)
    s.acquire_spectrum(); wait(lambda:not s._spectrometer_busy and not s._async_tasks)
    assert s.latest_result.settings.backend=="simulation" and not errors
    assert list((Path(sys.argv[1])/"Spectra").glob("synthetic_*.npz"))
    w.tabs.setCurrentIndex(0)
    m.x_points.setValue(30); m.y_points.setValue(30); m.start_new()
    wait(lambda:m.progress.value()>0 or not m.map_controller.busy)
    assert m.map_controller.busy
    w.refresh_activity(); assert w.stop_all_button.isEnabled()
    # Closing requests cancellation, but must not destroy an active QThread.
    assert not w.close()
    wait(lambda:not busy_workflows(w.pages))
    assert not errors
    assert w.close()
    assert not w._activity_timer.isActive()
    print("UNIFIED SIMULATION WORKSPACE PASSED")
finally:
    if busy_workflows(w.pages): w.stop_all(); wait(lambda:not busy_workflows(w.pages))
    w.close(); app.processEvents()
'''
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg")
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UNIFIED SIMULATION WORKSPACE PASSED" in result.stdout
