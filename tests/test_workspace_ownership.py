"""Existing session reservation semantics and workspace adapter lifecycle."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from labtools.runtime.session import ResourceBusyError
from labtools.simulation.ownership import WorkspaceOwnership

ROOT = Path(__file__).resolve().parents[1]


def test_reservation_conflict_cancel_cleanup_and_reuse():
    ownership = WorkspaceOwnership()
    lease = ownership.reserve("Intensity map")
    try:
        status = ownership.status().resources[0]
        assert status.owner == "Intensity map" and not status.connected
        with pytest.raises(ResourceBusyError):
            ownership.reserve("Spectrum")
        # A cancellation request is not lease release; teardown still owns it.
        with pytest.raises(ResourceBusyError):
            ownership.close()
        lease.release()
        with ownership.reserve("Spectrum"):
            assert ownership.status().resources[0].owner == "Spectrum"
        assert ownership.status().resources[0].state == "available"
    finally:
        lease.release()
        ownership.close()


def method(class_name, name, base):
    tree = ast.parse((ROOT / "src/labtools/gui/workspace_panels.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    functions = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in {name, "_release_workspace_lease"}]
    namespace = {"Base": base, "ResourceBusyError": ResourceBusyError}
    module = ast.Module(body=[ast.ClassDef(name="Adapter", bases=[ast.Name(id="Base", ctx=ast.Load())], keywords=[], body=functions, decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "checked_in_adapter", "exec"), namespace)  # noqa: S102 - checked-in AST test only
    return namespace["Adapter"]


@pytest.mark.parametrize("outcome", ["started", "refused", "raises"])
def test_map_start_retains_until_idle_or_releases_failed_start(outcome):
    class Base:
        def _start_worker(self, config):
            if outcome == "raises":
                raise ValueError("start failed")
            self.map_controller.busy = outcome == "started"

    adapter = method("OwnedMapPanel", "_start_worker", Base)()
    ownership = WorkspaceOwnership()
    adapter._ownership = ownership
    adapter._workspace_lease = None
    adapter.map_controller = SimpleNamespace(busy=False)
    adapter.set_status = lambda text: None
    try:
        if outcome == "raises":
            with pytest.raises(ValueError):
                adapter._start_worker(object())
        else:
            adapter._start_worker(object())
        assert (adapter._workspace_lease is not None) == (outcome == "started")
        if outcome == "started":
            with pytest.raises(ResourceBusyError):
                ownership.reserve("Spectrum")
            adapter.map_controller.busy = False
            adapter._release_workspace_lease()
        assert ownership.status().resources[0].state == "available"
    finally:
        adapter._release_workspace_lease()
        ownership.close()


def test_spectrum_conflict_never_starts_worker():
    class Base:
        def _start_operation(self, *args):
            pytest.fail("Conflicting operation must not start")

    adapter = method("OwnedSpectrumPanel", "_start_operation", Base)()
    ownership = WorkspaceOwnership()
    adapter._ownership = ownership
    adapter._workspace_lease = None
    adapter._spectrometer_busy = False
    adapter._async_tasks = []
    messages = []
    adapter.set_status = messages.append
    try:
        with ownership.reserve("Intensity map"):
            adapter._start_operation(None, None, None, "start")
            assert "Workspace busy" in messages[-1]
            assert adapter._workspace_lease is None
    finally:
        ownership.close()


def test_spectrum_releases_after_thread_cleanup_not_result():
    class Base:
        def _thread_finished(self, task):
            self._async_tasks.remove(task)

    adapter = method("OwnedSpectrumPanel", "_thread_finished", Base)()
    ownership = WorkspaceOwnership()
    task = object()
    adapter._ownership = ownership
    adapter._workspace_lease = ownership.reserve("Spectrum")
    adapter._async_tasks = [task]
    try:
        with pytest.raises(ResourceBusyError):
            ownership.reserve("Intensity map")
        adapter._thread_finished(task)
        assert adapter._workspace_lease is None
        assert ownership.status().resources[0].state == "available"
    finally:
        adapter._release_workspace_lease()
        ownership.close()


def test_workspace_does_not_overwrite_restored_grid():
    source = (ROOT / "src/labtools/gui/workspace.py").read_text(encoding="utf-8")
    assert "mapping.x_points.setValue" not in source
    assert "mapping.y_points.setValue" not in source


def test_actual_workspace_conflict_cancel_release_and_grid_memory(tmp_path):
    import importlib.util
    import os
    import subprocess
    import sys

    if importlib.util.find_spec("PyQt6") is None:
        pytest.skip("PyQt6 unavailable: actual workspace integration remains unassessed")
    code = r'''
import builtins, sys, time
from pathlib import Path
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if any(name==p or name.startswith(p+".") for p in ("labtools.devices","horiba_sdk","u6","pyvisa","serial")):
        raise AssertionError("Native import forbidden: "+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from PyQt6 import QtCore
from PyQt6.QtWidgets import QApplication
from labtools.gui.workspace import SimulationWorkspace
from labtools.simulation.workspace import busy_workflows
root=Path(sys.argv[1]); original_settings=QtCore.QSettings
QtCore.QSettings=lambda org,name: original_settings(str(root/(name+".ini")),original_settings.Format.IniFormat)
app=QApplication([])
w=SimulationWorkspace(output_root=root/"outputs"); w.show()
m=w.pages["Intensity map"]; s=w.pages["Spectrum"]
errors=[]; m.map_controller.failed.connect(lambda *a:errors.append(a)); s._show_error=lambda *a:errors.append(a)
def wait(predicate):
    end=time.monotonic()+20
    while not predicate():
        app.processEvents(); time.sleep(.005)
        assert time.monotonic()<end,"Workspace did not finish"
    app.processEvents()
try:
    m.x_points.setValue(30); m.y_points.setValue(31); m.integration.setValue(.02); m.settle.setValue(0)
    m.start_new(); wait(lambda:m.progress.value()>0 or not m.map_controller.busy)
    assert m.map_controller.busy
    assert w.ownership.status().resources[0].owner=="Intensity map"
    s.acquire_spectrum()
    assert not s._async_tasks and "Workspace busy" in s.status.text()
    w.stop_all()
    # Stop request itself must not release before QThread teardown.
    assert w.ownership.status().resources[0].owner=="Intensity map"
    wait(lambda:not busy_workflows(w.pages))
    assert w.ownership.status().resources[0].owner is None
    s.acquire_spectrum(); wait(lambda:not busy_workflows(w.pages))
    assert s.latest_result is not None and not errors
    assert w.ownership.status().resources[0].owner is None
    assert w.close()
    assert w.ownership.status().state=="closed"
    reopened=SimulationWorkspace(output_root=root/"outputs")
    try:
        assert reopened.pages["Intensity map"].x_points.value()==30
        assert reopened.pages["Intensity map"].y_points.value()==31
    finally:
        reopened.close()
    print("OWNERSHIP AND GRID MEMORY PASSED")
finally:
    if busy_workflows(w.pages):w.stop_all();wait(lambda:not busy_workflows(w.pages))
    w.close();app.processEvents()
'''
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg")
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OWNERSHIP AND GRID MEMORY PASSED" in result.stdout


@pytest.mark.parametrize("outcome", ["started", "refused", "raises"])
def test_spectrum_start_failure_or_refusal_releases_reservation(outcome):
    class Base:
        def _start_operation(self, *args):
            if outcome == "raises":
                raise ValueError("worker startup failed")
            if outcome == "started":
                self._async_tasks.append(object())

    adapter = method("OwnedSpectrumPanel", "_start_operation", Base)()
    ownership = WorkspaceOwnership()
    adapter._ownership = ownership
    adapter._workspace_lease = None
    adapter._spectrometer_busy = False
    adapter._async_tasks = []
    adapter.set_status = lambda text: None
    try:
        if outcome == "raises":
            with pytest.raises(ValueError):
                adapter._start_operation(None, None, None, "start")
        else:
            adapter._start_operation(None, None, None, "start")
        assert (adapter._workspace_lease is not None) == (outcome == "started")
    finally:
        adapter._async_tasks.clear()
        adapter._release_workspace_lease()
        ownership.close()
