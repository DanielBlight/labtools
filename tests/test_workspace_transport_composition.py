"""Both transport boundaries in one configured workspace, with fake transports only."""

import asyncio
import builtins
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from labtools.config.intensity_map import IntensityMapConfig
from labtools.config.spectrum import SpectrumSettings
from labtools.config.workspace import WorkspaceConfig
from labtools.simulation.ownership import WorkspaceOwnership
from labtools.simulation.transport_composition import (
    FakeTransportComposition,
    rehearse_composition,
)
from labtools.simulation.transport_fakes import single_capture_stitch

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def forbid_native_imports(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "u6", "serial", "pyvisa")):
            raise AssertionError("Native import forbidden in composition: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.mark.parametrize("disjoint", [False, True])
def test_complete_headless_composition_and_saved_provenance(tmp_path, disjoint):
    config = WorkspaceConfig()
    if disjoint:
        config = replace(config, resources=("map", "spec"), map_resources=("map",), spectrum_resources=("spec",))
    report = rehearse_composition(tmp_path, config)
    assert report["status"] == "passed"
    assert len(report["checks"]) == 10 and all(report["checks"].values())
    output = Path(report["output_directory"])
    assert json.loads((output / "rehearsal.json").read_text())["status"] == "passed"
    with np.load(output / "corrected_spectrum.npz", allow_pickle=False) as data:
        metadata = json.loads(str(data["metadata"].item()))
        assert metadata["synthetic_data"]
        assert metadata["settings"]["backend"] == "simulation"
    for metadata_path in output.glob("Maps/SIMULATION/*/intensity_map_metadata.json"):
        metadata = json.loads(metadata_path.read_text())
        assert metadata["synthetic_data"] and metadata["backend"] == "simulation"
    for archive in output.glob("Maps/SIMULATION/*/intensity_map_complete.npz"):
        with np.load(archive, allow_pickle=False) as data:
            assert bool(data["synthetic_data"])
            assert str(data["backend"].item()) == "simulation"
    assert {event["resource"] for event in report["events"]} == {"labjack", "counter", "mirror", "gate", "spectrometer"}


def test_refusals_happen_before_transports_or_outputs(tmp_path):
    composition = FakeTransportComposition()
    mapping = IntensityMapConfig(-1, 1, 2, -1, 1, 2, backend="simulation", output_root=tmp_path / "maps")
    with pytest.raises(RuntimeError, match="Bind"):
        composition.acquire_map(mapping)
    ownership = WorkspaceOwnership()
    composition.bind(ownership)
    try:
        with pytest.raises(PermissionError):
            composition.acquire_map(mapping)
        with pytest.raises(ValueError):
            composition.acquire_map(replace(mapping, backend="real"))
        with pytest.raises(RuntimeError, match="already bound"):
            composition.bind(ownership)
        assert not composition.trace.events()
        assert not (tmp_path / "maps").exists()
    finally:
        ownership.close()


def test_spectrum_identity_and_real_request_refused():
    composition = FakeTransportComposition()
    ownership = WorkspaceOwnership()
    composition.bind(ownership)
    settings = SpectrumSettings(configuration_id="wrong", backend="simulation", preset="syncerity",
                                exposure_s=.065, gain=0, speed=0, slit_width_mm=.1, start_nm=500, end_nm=600)
    try:
        with ownership.reserve("Spectrum"):
            with pytest.raises(ValueError, match="configuration_id"):
                asyncio.run(composition.spectrum.acquire(settings))
            with pytest.raises(ValueError, match="simulation requests"):
                asyncio.run(composition.spectrum.acquire(replace(settings, backend="real")))
        assert not composition.trace.events()
    finally:
        ownership.close()


def test_fake_stitcher_does_not_silently_emulate_vendor_stitching():
    with pytest.raises(ValueError, match="one spectral centre"):
        single_capture_stitch([], 500, 600)
    with pytest.raises(ValueError, match="cover"):
        single_capture_stitch([[[500], [[1]]]], 600, 700)


def test_headless_cli_uses_same_composition(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), MPLBACKEND="Agg")
    result = subprocess.run(
        [sys.executable, "-m", "labtools.cli", "simulate", "workspace", "--rehearse-transports", "--output", str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "passed" and report["synthetic_data"]


def test_actual_qt_composed_workflows_recovery_and_memory(tmp_path):
    pytest.importorskip(
        "PyQt6.QtWidgets", reason="Qt runtime unavailable: actual GUI acceptance remains unassessed",
        exc_type=ImportError,
    )
    code = r'''
import builtins, json, sys, time
from pathlib import Path
from threading import get_ident
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if any(name==p or name.startswith(p+".") for p in ("labtools.devices","horiba_sdk","u6","serial","pyvisa")):
        raise AssertionError("Native import forbidden: "+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from PyQt6 import QtCore
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox
from labtools.gui.workspace import SimulationWorkspace
from labtools.simulation.workspace import busy_workflows
from labtools.simulation.transport_composition import FakeTransportComposition
from labtools.io.spectrum_records import load_dark_record
import numpy as np
root=Path(sys.argv[1]); original_settings=QtCore.QSettings
QtCore.QSettings=lambda org,name: original_settings(str(root/(name+".ini")),original_settings.Format.IniFormat)
app=QApplication([]); ui_thread=get_ident()
QMessageBox.warning=lambda *a,**k:QMessageBox.StandardButton.Ok
QMessageBox.critical=lambda *a,**k:QMessageBox.StandardButton.Ok
QMessageBox.exec=lambda *a,**k:QMessageBox.StandardButton.Ok
services=FakeTransportComposition()
w=SimulationWorkspace(output_root=root/"outputs",map_acquisition=services.acquire_map,spectrum_service=services.spectrum)
services.bind(w.ownership);w.show()
m=w.pages["Intensity map"];s=w.pages["Spectrum"]
map_results=[];map_errors=[];spectrum_errors=[]
m.map_controller.finished.connect(map_results.append)
m.map_controller.failed.connect(lambda *a:map_errors.append(a))
s._show_error=lambda *a:spectrum_errors.append(a)
QFileDialog.getSaveFileName=lambda *a,**k:(str(root/"dark.npz"),"")
def wait(predicate,timeout=30):
    end=time.monotonic()+timeout
    while not predicate():
        app.processEvents();time.sleep(.005)
        assert time.monotonic()<end,"Composed Qt workflow did not finish"
    app.processEvents()
def idle():return not busy_workflows(w.pages)
try:
    assert m.simulation_mode.isChecked() and not m.simulation_mode.isEnabled()
    assert not m.laser_group.isEnabled() and not s.laser_group.isEnabled()
    m.x_points.setValue(3);m.y_points.setValue(3);m.integration.setValue(.02);m.settle.setValue(0)
    m.save_results.setChecked(True);m.start_new();wait(idle)
    assert map_results[-1].complete and not map_errors
    first=map_results[-1].output_directory
    m.x_points.setValue(20);m.y_points.setValue(21);m.start_new()
    wait(lambda:m.progress.value()>0 or not m.map_controller.busy)
    assert m.map_controller.busy
    w.tabs.setCurrentIndex(1);s.acquire_spectrum()
    assert not s._async_tasks and "Workspace busy" in s.status.text()
    assert not w.close();wait(idle)
    stopped=map_results[-1];assert not stopped.complete
    assert w.ownership.status().resources[0].owner is None
    QFileDialog.getExistingDirectory=lambda *a,**k:str(stopped.output_directory)
    m.choose_resume();wait(idle)
    assert map_results[-1].complete and map_results[-1].resumed
    m.x_points.setValue(3);m.y_points.setValue(4)
    services.trace.fail_next("counter","read");m.start_new();wait(idle)
    assert len(map_errors)==1 and w.ownership.status().resources[0].owner is None
    m.start_new();wait(idle);assert map_results[-1].complete
    s.save_csv.setChecked(True);s.save_png.setChecked(True)
    s.acquire_spectrum();wait(idle);raw=s.latest_result.intensity.copy()
    assert "SYNTHETIC" in s.ax.get_title()
    s.capture_reusable_dark();wait(idle)
    dark=load_dark_record(root/"dark.npz");assert dark.settings.backend=="simulation"
    s.clear_pre_taken_dark()
    QFileDialog.getOpenFileName=lambda *a,**k:(str(root/"dark.npz"),"")
    s.load_pre_taken_dark();s.use_background.setChecked(True);s.background_mode.setCurrentIndex(1)
    s.acquire_spectrum();wait(idle);corrected=s.latest_result.intensity.copy()
    np.testing.assert_allclose(corrected,raw-dark.intensity)
    s.acquire_spectrum();wait(idle);np.testing.assert_array_equal(corrected,s.latest_result.intensity)
    services.trace.fail_next("spectrometer","acquire");s.acquire_spectrum();wait(idle)
    assert len(spectrum_errors)==1 and w.ownership.status().resources[0].owner is None
    s.acquire_spectrum();wait(idle)
    assert len(spectrum_errors)==1
    for path in (root/"outputs/Spectra").glob("synthetic_*.npz"):
        with np.load(path,allow_pickle=False) as archive:
            metadata=json.loads(str(archive["metadata"].item()))
            assert metadata["synthetic_data"] and metadata["settings"]["backend"]=="simulation"
    metadata=json.loads((first/"intensity_map_metadata.json").read_text())
    assert metadata["backend"]=="simulation" and metadata["synthetic_data"]
    assert all(e["thread"]!=ui_thread for e in services.trace.events())
    groups={}
    for e in services.trace.events():groups.setdefault(e["handle"],[]).append(e)
    for group in groups.values():assert len({(e["thread"],e["loop"]) for e in group})==1
    w.grab().save(str(root/"workspace.png"))
    assert w.close()
    reopened=SimulationWorkspace(output_root=root/"outputs")
    try:
        assert reopened.pages["Intensity map"].x_points.value()==3
        assert reopened.pages["Intensity map"].y_points.value()==4
    finally:reopened.close()
    print("COMPOSED QT WORKSPACE PASSED")
finally:
    if not idle():w.stop_all();wait(idle)
    w.close();app.processEvents()
'''
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg")
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPOSED QT WORKSPACE PASSED" in result.stdout


def test_gui_cli_selects_both_fixed_fake_services(monkeypatch, tmp_path):
    from types import ModuleType

    from labtools.cli import main

    windows = []

    class App:
        def __init__(self, args):
            pass

        def exec(self):
            return 0

    class Window:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.ownership = WorkspaceOwnership(kwargs["config"])
            windows.append(self)

        def setWindowTitle(self, title):
            self.title = title

        def show(self):
            self.shown = True

    widgets = ModuleType("PyQt6.QtWidgets")
    widgets.QApplication = App
    gui = ModuleType("labtools.gui.workspace")
    gui.SimulationWorkspace = Window
    monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", widgets)
    monkeypatch.setitem(sys.modules, "labtools.gui.workspace", gui)
    try:
        with pytest.raises(SystemExit) as caught:
            main(["simulate", "workspace", "--transport-contracts", "--output", str(tmp_path)])
        assert caught.value.code == 0
        window = windows[0]
        composition = window.kwargs["map_acquisition"].__self__
        assert isinstance(composition, FakeTransportComposition)
        assert composition._ownership is window.ownership
        assert window.kwargs["spectrum_service"] is composition.spectrum
        assert "FAKE TRANSPORT" in window.title and window.shown
        assert not composition.trace.events()
    finally:
        for window in windows:
            window.ownership.close()
