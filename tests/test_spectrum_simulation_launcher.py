"""Synthetic spectrum entry and presentation contracts without native imports."""

import ast
import csv
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from labtools.acquisition.spectrum_service import SpectrumResult
from labtools.config.spectrum import SpectrumSettings
from labtools.io.spectrum_records import save_spectrum_result
from labtools.simulation import spectrum

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_gui(monkeypatch):
    windows = []

    class Field:
        def setValue(self, value):
            self.value = value

        def setText(self, value):
            self.value = value

    class Window:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.start_wl = Field()
            self.end_wl = Field()
            self.exposure_box = Field()
            self.output_directory = Field()
            windows.append(self)

        def show(self):
            self.shown = True

    class App:
        def __init__(self, args):
            pass

        def exec(self):
            return 0

    qt = ModuleType("PyQt6")
    qt.__path__ = []
    widgets = ModuleType("PyQt6.QtWidgets")
    widgets.QApplication = App
    gui = ModuleType("labtools.gui.spectrum_gui_horiba")
    gui.HoribaRangeWindow = Window
    for name, module in {"PyQt6": qt, "PyQt6.QtWidgets": widgets, "labtools.gui.spectrum_gui_horiba": gui}.items():
        monkeypatch.setitem(sys.modules, name, module)
    return windows


def test_cli_launches_only_synthetic_window(fake_gui, tmp_path):
    from labtools.cli import main

    with pytest.raises(SystemExit) as caught:
        main(["simulate", "spectrum", "--gui", "--output", str(tmp_path)])
    assert caught.value.code == 0
    window = fake_gui[0]
    assert window.kwargs["backend"] == "simulation"
    assert window.kwargs["configuration_id"] == "toy-scene-v1"
    assert window.kwargs["preset_options"] is spectrum.TOY_PRESET_OPTIONS
    assert window.start_wl.value == 500
    assert window.end_wl.value == 600
    assert window.exposure_box.value == 0.065
    assert window.output_directory.value == str(tmp_path)
    assert window.shown


def test_missing_gui_flag_fails_before_window(fake_gui):
    with pytest.raises(SystemExit) as caught:
        spectrum.main([])
    assert caught.value.code == 2
    assert not fake_gui


def extracted_method(name):
    """Exercise the actual method body without pretending to execute Qt widgets."""
    tree = ast.parse((ROOT / "src/labtools/gui/spectrum_gui_horiba.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "HoribaRangeWindow")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    method.decorator_list = []
    namespace = {
        "Path": Path, "SpectrumResult": SpectrumResult, "save_spectrum_result": save_spectrum_result,
        "csv": csv, "traceback": __import__("traceback"),
    }
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), method], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "actual_gui_method", "exec"), namespace)  # noqa: S102 - execute checked-in method AST in an isolated test namespace
    return namespace[name]


@pytest.mark.parametrize("name", ["connect_laser", "turn_laser_on", "turn_laser_off", "set_laser_current"])
def test_direct_laser_actions_return_before_hardware_access(name):
    messages = []
    fake = SimpleNamespace(_backend="simulation", set_status=messages.append)
    extracted_method(name)(fake)
    assert messages == ["Simulation mode: laser actions are unavailable."]


@pytest.mark.parametrize("backend", ["simulation", "real"])
def test_plot_and_exports_have_correct_backend_identity(tmp_path, backend):
    settings = SpectrumSettings(configuration_id="test", backend=backend, start_nm=500, end_nm=600, preset="syncerity", exposure_s=0.065, gain=0, speed=0, slit_width_mm=0.1)
    result = SpectrumResult(settings, [500, 600], [10, 20], [10, 20], "none", None)
    figure = Figure()
    canvas = FigureCanvasAgg(figure)
    axes = figure.subplots()
    fake = SimpleNamespace(
        _backend=backend, ax=axes, figure=figure, canvas=canvas,
        plot_meta=SimpleNamespace(setText=lambda text: None),
        _save_options=(True, True, tmp_path),
        _maybe_save_result=lambda value: extracted_method("_maybe_save_result")(fake, value),
        set_status=lambda text: None,
    )
    extracted_method("_style_empty_axes")(fake)
    extracted_method("_handle_acquire_done")(fake, result)
    prefix = "synthetic" if backend == "simulation" else "horiba"
    archive = next(tmp_path.glob(prefix + "_*.npz"))
    csv_path = archive.with_suffix(".csv")
    assert archive.with_suffix(".png").exists()
    first_line = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("# SYNTHETIC") == (backend == "simulation")
    assert ("SYNTHETIC" in axes.get_title()) == (backend == "simulation")
    assert ("arbitrary" in axes.get_ylabel()) == (backend == "simulation")
    with np.load(archive, allow_pickle=False) as data:
        assert json.loads(str(data["metadata"].item()))["synthetic_data"] == (backend == "simulation")


def test_actual_offscreen_spectrum_window(tmp_path):
    """Use real Qt and existing simulation service when installed; never real devices."""
    import importlib.util
    import os
    import subprocess

    if importlib.util.find_spec("PyQt6") is None:
        pytest.skip("PyQt6 unavailable: actual operator-window execution remains unassessed")
    code = r'''
import builtins, json, sys, time
from pathlib import Path
original = builtins.__import__
def guarded(name, *args, **kwargs):
    blocked = ("labtools.devices", "horiba_sdk", "u6", "pyvisa", "serial")
    if any(name == prefix or name.startswith(prefix + ".") for prefix in blocked):
        raise AssertionError("Hardware import forbidden: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from PyQt6.QtWidgets import QApplication, QFileDialog
from labtools.gui.spectrum_gui_horiba import HoribaRangeWindow
import numpy as np
app = QApplication([])
root = Path(sys.argv[1])
w = HoribaRangeWindow(backend="simulation", configuration_id="toy-scene-v1")
w.start_wl.setValue(500); w.end_wl.setValue(600); w.exposure_box.setValue(.065)
w.output_directory.setText(str(root)); w.save_csv.setChecked(True); w.save_png.setChecked(True)
errors=[]
w._show_error=lambda *args: errors.append(args)
QFileDialog.getSaveFileName=lambda *a,**k:(str(root/"dark.npz"), "")
def wait():
    end=time.monotonic()+15
    while w._spectrometer_busy or w._async_tasks:
        app.processEvents(); time.sleep(.005)
        assert time.monotonic()<end, "Synthetic worker did not finish"
    app.processEvents()
try:
    assert "SIMULATION" in w.windowTitle() and not w.laser_group.isEnabled()
    for name in ("connect_laser", "turn_laser_on", "turn_laser_off", "set_laser_current"):
        getattr(w,name)()
    assert w.laser is None
    w.acquire_spectrum(); wait(); raw=w.latest_result.intensity.copy()
    assert "SYNTHETIC" in w.ax.get_title()
    w.capture_reusable_dark(); wait(); dark=w.pre_taken_dark
    assert (root/"dark.npz").exists()
    w.use_background.setChecked(True); w.background_mode.setCurrentIndex(1)
    w.acquire_spectrum(); wait(); corrected=w.latest_result.intensity.copy()
    np.testing.assert_allclose(corrected, raw-dark.intensity)
    w.acquire_spectrum(); wait(); np.testing.assert_array_equal(corrected,w.latest_result.intensity)
    assert not errors
    assert len(list(root.glob("synthetic_*.npz")))==3
    assert len(list(root.glob("synthetic_*.png")))==3
    assert all(p.read_text().startswith("# SYNTHETIC") for p in root.glob("synthetic_*.csv"))
    print("ACTUAL SYNTHETIC SPECTRUM WINDOW PASSED")
finally:
    if w._spectrometer_busy: w.request_stop(); wait()
    w.close(); app.processEvents()
'''
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg")
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ACTUAL SYNTHETIC SPECTRUM WINDOW PASSED" in result.stdout
