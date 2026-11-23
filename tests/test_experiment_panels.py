"""Actual unified Qt tabs, small simulated runs and responsive plot geometry."""

import shutil
import time
from pathlib import Path

import pytest

pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)
from PyQt6.QtWidgets import QApplication, QFormLayout, QMessageBox

from labtools.gui.native_workspace import create_window
from labtools.runtime.session import ResourceBusyError
from labtools.simulation.operator_session import SimulatedOperatorSession

ROOT = Path(__file__).resolve().parents[1]


def spin(app, predicate):
    deadline = time.monotonic() + 8
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, "Experiment GUI timed out"
        time.sleep(0.002)
    app.processEvents()


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    workspace = SimulatedOperatorSession(tmp_path / "bundle/candidate.json", preferences_path=tmp_path / "p.json", output_root=tmp_path, realtime=False)
    widget = create_window(workspace)
    widget.show()
    app.processEvents()
    widget.pages["Intensity map"].x_points.setValue(2)
    widget.pages["Intensity map"].y_points.setValue(2)
    widget.pages["Annealing"].x_points.setValue(1)
    widget.pages["Annealing"].y_points.setValue(1)
    widget.pages["Annealing"].passes.setValue(1)
    widget.pages["Hyperspectral"].x_points.setValue(2)
    widget.pages["Hyperspectral"].y_points.setValue(2)
    widget.pages["Hyperspectral"].output.setText(str(tmp_path / "cubes"))
    widget.pages["Sequences"].output.setText(str(tmp_path / "sequences"))
    yield app, widget, workspace
    widget.stop_all()
    spin(app, lambda: not widget.any_busy())
    widget.close()
    spin(app, lambda: workspace._closed)


def test_program_preview_and_single_point_run(window):
    app, widget, _ = window
    panel = widget.pages["Anneal programs"]
    panel.preview()
    assert "1 point exposures" in panel.log.toPlainText()
    panel.start()
    spin(app, lambda: not panel.busy)
    assert panel.last_result["status"] == "completed"
    assert panel.last_result["completed_points"] == 1


def test_cube_panel_acquires_selectable_spectra_and_releases(window):
    app, widget, workspace = window
    panel = widget.pages["Hyperspectral"]
    panel.start()
    spin(app, lambda: not panel.busy)
    assert panel.last_result is not None, panel.status.text()
    assert panel.last_result.completed_points == 4
    panel.show_pixel(1, 1)
    assert "X=1, Y=1" in panel.spectrum_axes.get_title()
    assert all(state.owner is None for state in workspace._ownership.status().resources)


@pytest.mark.parametrize("measurement", ["Spectrum", "Intensity map", "Hyperspectral"])
def test_sequence_tab_runs_each_measurement(window, measurement):
    app, widget, _ = window
    panel = widget.pages["Sequences"]
    panel.measurement.setCurrentText(measurement)
    panel.cycles.setValue(2)
    panel.start()
    spin(app, lambda: not panel.busy)
    assert panel.last_result is not None, panel.status.text()
    assert panel.last_result["status"] == "completed"
    assert len(panel.last_result["steps"]) == 5


def test_sequence_stop_all_and_close_wait_for_task(window):
    app, widget, workspace = window
    panel = widget.pages["Sequences"]
    panel.cycles.setValue(100)
    panel.start()
    assert widget.any_busy()
    widget.stop_all()
    widget.close()
    spin(app, lambda: workspace._closed)
    assert panel.last_result["status"] == "cancelled"


def test_busy_cube_refuses_overlapping_workflow(window):
    app, widget, workspace = window
    panel = widget.pages["Hyperspectral"]
    panel.start()
    assert panel.busy
    with pytest.raises(ResourceBusyError):
        workspace._ownership.reserve("Annealing")
    widget.stop_all()
    spin(app, lambda: not widget.any_busy())


def test_camera_form_wrap_and_narrow_map_label_bounds(window):
    app, widget, _ = window
    camera = widget.camera_window
    forms = camera.findChildren(QFormLayout)
    assert forms and all(form.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapAllRows for form in forms)
    mapping = widget.pages["Intensity map"]
    widget.tabs.setCurrentWidget(mapping)
    widget.resize(820, 650)
    app.processEvents()
    from labtools.gui.compact_plot import repair_plot_geometry

    repair_plot_geometry(mapping)
    mapping.canvas.draw()
    bounds = mapping.axes.yaxis.label.get_window_extent(mapping.canvas.get_renderer())
    assert bounds.x0 >= 0
    assert mapping.axes.get_position().width > 0


def test_workspace_settings_roundtrip_includes_new_tabs(window, tmp_path):
    _, widget, _ = window
    program = widget.pages["Anneal programs"]
    sequence = widget.pages["Sequences"]
    cube = widget.pages["Hyperspectral"]
    program.mode.setCurrentText("Dwell ramp array")
    program.first_dwell.setValue(0.01)
    program.last_dwell.setValue(0.1)
    program.spacing.setCurrentText("Logarithmic")
    sequence.cycles.setValue(3)
    cube.dark.setCurrentText("per_frame")
    path = tmp_path / "settings.json"
    widget.workspace_hub.export_settings(path)
    program.first_dwell.setValue(1)
    sequence.cycles.setValue(1)
    cube.dark.setCurrentText("none")
    widget.workspace_hub.load_settings(path)
    assert program.first_dwell.value() == 0.01
    assert sequence.cycles.value() == 3
    assert cube.dark.currentText() == "per_frame"
