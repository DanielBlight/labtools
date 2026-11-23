"""Optional run output and post-run exports, with no device reacquisition."""

import json
from dataclasses import replace

import numpy as np
import pytest
from PyQt6.QtWidgets import QFileDialog
from test_experiment_panels import spin
from test_experiment_workflows import cube, program

from labtools.runtime.experiment_workflows import run_sequence
from labtools.runtime.retained_results import export_retained

pytest_plugins = ["test_experiment_panels", "test_experiment_workflows"]


@pytest.mark.parametrize("measurement", ["Spectrum", "Intensity map", "Hyperspectral"])
def test_full_sequence_retained_and_saved_afterwards(workspace, tmp_path, measurement):
    request = cube(workspace) if measurement == "Hyperspectral" else workspace.workflows.spectrum_settings() if measurement == "Spectrum" else replace(workspace.workflows.map_config(), x_points=2, y_points=2, integration_time_s=0.001)
    before = set(tmp_path.rglob('*'))
    result = run_sequence(workspace, program(workspace), measurement, request, cycles=2, save_output=False)
    assert set(tmp_path.rglob('*')) == before
    assert len(result["retained_steps"]) == 5
    assert result["retained_steps"][0]["role"] == "baseline"
    path = export_retained(tmp_path / "exports", result, label="sequence")
    doc = json.loads((path / "run.json").read_text())
    assert len(doc["result"]["retained_steps"]) == 5
    with np.load(path / "arrays.npz", allow_pickle=False) as archive:
        assert archive.files
        assert all(archive[key].dtype != object for key in archive.files)
    second = export_retained(tmp_path / "exports", result, label="sequence")
    assert second != path


def test_cube_optional_output_and_save_button(window, tmp_path, monkeypatch):
    app, widget, _ = window
    panel = widget.pages["Hyperspectral"]
    panel.save_output.setChecked(False)
    panel.output.setText(str(tmp_path / "no-cube-output"))
    panel.start()
    spin(app, lambda: not panel.busy)
    assert panel.last_result.completed_points == 4
    assert not (tmp_path / "no-cube-output").exists()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path / "saved"))
    panel.save_result_button.click()
    assert len(list((tmp_path / "saved").glob('*/run.json'))) == 1
    assert panel.last_result.completed_points == 4


@pytest.mark.parametrize("measurement, axes", [("Spectrum", 1), ("Intensity map", 1), ("Hyperspectral", 2)])
def test_sequence_plot_uses_whole_area(window, measurement, axes):
    app, widget, _ = window
    panel = widget.pages["Sequences"]
    panel.measurement.setCurrentText(measurement)
    panel.save_output.setChecked(False)
    panel.start()
    spin(app, lambda: not panel.busy)
    panel.canvas.draw()
    assert len(panel.figure.axes) == axes
    if axes == 1:
        bounds = panel.figure.axes[0].get_subplotspec().get_gridspec()
        assert bounds.ncols == 1
    assert "retained_steps" not in panel.log.toPlainText()


def test_annealing_instruments_and_output_visible_without_scroll(window):
    app, widget, _ = window
    panel = widget.pages["Annealing"]
    widget.resize(1400, 760)
    widget.tabs.setCurrentWidget(panel)
    app.processEvents()
    assert panel.instruments_card.isVisible() and panel.output_card.isVisible()
    assert panel.output_card.mapTo(panel, panel.output_card.rect().bottomRight()).y() < panel.height()
    assert panel.output_card.mapTo(panel, panel.output_card.rect().topLeft()).x() > panel.width() / 3
    assert panel.output_root.isVisible()


def test_map_no_output_then_save_without_reacquisition(window, tmp_path, monkeypatch):
    app, widget, _ = window
    panel = widget.pages["Intensity map"]
    panel.save_results.setChecked(False)
    config = replace(panel._config(), output_root=tmp_path / "no-map", integration_time_s=0.001)
    panel._start_worker(config)
    spin(app, lambda: not panel.map_controller.busy)
    assert not (tmp_path / "no-map").exists()
    retained = panel.retained_run.get()
    assert retained["result"].complete
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path / "saved-map"))
    panel.save_retained_button.click()
    assert list((tmp_path / "saved-map").glob('*/arrays.npz'))
    assert panel.retained_run.get() is retained


def test_anneal_no_output_then_save(window, tmp_path, monkeypatch):
    app, widget, _ = window
    panel = widget.pages["Annealing"]
    program_panel = widget.pages["Anneal programs"]
    panel.save_log.setChecked(False)
    panel.output_root.setText(str(tmp_path / "no-anneal"))
    program_panel.mode.setCurrentText("Single point")
    panel.start_button.click()
    spin(app, lambda: not program_panel.busy)
    assert not (tmp_path / "no-anneal").exists()
    assert panel.retained_run.get() is not None
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path / "saved-anneal"))
    # Save is gated by a UI timer, allow its first refresh.
    spin(app, lambda: panel.save_retained_button.isEnabled())
    panel.save_retained_button.click()
    assert list((tmp_path / "saved-anneal").glob('*/run.json'))


def test_spectrum_no_automatic_output_and_save_after_run(window, tmp_path, monkeypatch):
    app, widget, _ = window
    panel = widget.pages["Spectrum"]
    panel.save_csv.setChecked(False)
    panel.save_png.setChecked(False)
    before = set(tmp_path.rglob('*'))
    panel.acquire_button.click()
    spin(app, lambda: not panel._async_tasks)
    assert panel.retained_run.get() is not None
    assert set(tmp_path.rglob('*')) == before
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path / "saved-spectrum"))
    spin(app, lambda: panel.save_retained_button.isEnabled())
    panel.save_retained_button.click()
    assert list((tmp_path / "saved-spectrum").glob('*/arrays.npz'))


def test_uniform_anneal_optional_output_and_retention(window, tmp_path):
    app, widget, _ = window
    panel = widget.pages["Annealing"]
    widget.pages["Anneal programs"].mode.setCurrentText("Uniform array")
    panel.save_log.setChecked(False)
    panel.output_root.setText(str(tmp_path / "no-uniform"))
    panel.start_button.click()
    spin(app, lambda: panel._thread is None)
    assert not (tmp_path / "no-uniform").exists()
    assert panel.retained_run.get()["result"].completed


def test_failed_export_keeps_retained_data_and_unique_path(tmp_path):
    from labtools.gui.retained_run_controls import Retention
    value = {"data": np.array([1.0, np.nan]), "status": "cancelled"}
    retention = Retention()
    retention.set(value)
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    with pytest.raises(OSError):
        export_retained(blocker, retention.get())
    assert retention.get() is value
    path = export_retained(tmp_path, retention.get())
    with np.load(path / "arrays.npz", allow_pickle=False) as archive:
        np.testing.assert_equal(archive['array_000000'], value['data'])
