"""Offscreen operator rehearsal using the existing synthetic acquisition backend."""

import json
import time

import numpy as np
import pytest

pytest.importorskip("PyQt6")

from PyQt6 import QtCore
from PyQt6.QtWidgets import QApplication, QFileDialog

from labtools.acquisition.intensity_map import CHECKPOINT_FILENAME, METADATA_FILENAME
from labtools.gui.intensity_map_gui import IntensityMapWindow


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    original = QtCore.QSettings
    monkeypatch.setattr(
        QtCore, "QSettings",
        lambda org, name: original(str(tmp_path / f"{org}-{name}.ini"), original.Format.IniFormat),
    )
    application = QApplication.instance() or QApplication([])
    return application


def wait_until(app, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Synthetic operator action did not finish within timeout")


def make_window(tmp_path):
    window = IntensityMapWindow(
        simulation_only=True, simulation_seed=42, simulation_realtime=True,
    )
    window.output_root.setText(str(tmp_path / "maps"))
    window.x_points.setValue(5)
    window.y_points.setValue(5)
    window.integration.setValue(0.02)
    window.settle.setValue(0)
    window.save_results.setChecked(True)
    return window


def test_simulation_mode_stays_locked_and_preferences_are_isolated(app, tmp_path):
    window = make_window(tmp_path)
    try:
        assert window.simulation_mode.isChecked()
        assert not window.simulation_mode.isEnabled()
        assert "SIMULATION" in window.windowTitle()
        assert not window.laser_group.isEnabled()
        window.simulation_mode.setChecked(False)
        assert window.simulation_mode.isChecked()
        assert window._config().backend == "simulation"
        assert window._config().simulation_seed == 42
        assert window._config().simulation_realtime
        window._cleanup_worker()
        assert not window.simulation_mode.isEnabled()
        window.x_points.setValue(17)
        window._save_map_preferences()
        assert window._map_preferences.fileName().endswith("labtools-IntensityMapSimulation.ini")
    finally:
        window.close()
    reopened = IntensityMapWindow(simulation_only=True)
    try:
        assert reopened.x_points.value() == 17
        assert reopened.output_root.text() == str(tmp_path / "maps")
        real_settings = QtCore.QSettings("labtools", "IntensityMap")
        assert not real_settings.contains("preferences_v1/x_points")
    finally:
        reopened.close()


def test_complete_cancel_resume_and_repeat_synthetic_map(app, tmp_path, monkeypatch):
    window = make_window(tmp_path)
    results = []
    errors = []
    window.map_controller.finished.connect(results.append)
    window.map_controller.failed.connect(lambda message, details: errors.append(message))
    try:
        window.start_new()
        wait_until(app, lambda: not window.map_controller.busy)
        assert not errors
        assert results[-1].complete
        first = results[-1].output_directory
        assert "SYNTHETIC" in window.axes.get_title()
        assert window.progress.value() == 100
        for name in ["intensity_map_points.csv", "intensity_map_complete.npz", "summed_intensity_map.png", "SYNTHETIC_DATA.txt"]:
            assert (first / name).is_file()
        metadata = json.loads((first / METADATA_FILENAME).read_text(encoding="utf-8"))
        assert metadata["backend"] == "simulation"
        assert metadata["simulation_seed"] == 42
        assert metadata["synthetic_data"]

        window.x_points.setValue(20)
        window.y_points.setValue(20)
        window.start_new()
        wait_until(app, lambda: window.progress.value() > 0 or not window.map_controller.busy)
        assert window.map_controller.busy
        window.request_stop()
        wait_until(app, lambda: not window.map_controller.busy)
        stopped = results[-1]
        assert not stopped.complete
        assert (stopped.output_directory / CHECKPOINT_FILENAME).is_file()
        window.integration.setValue(0.001)  # resume restores the checkpoint's settings
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(stopped.output_directory))
        window.choose_resume()
        wait_until(app, lambda: not window.map_controller.busy, timeout=30)
        assert not errors
        assert results[-1].complete and results[-1].resumed
        assert results[-1].output_directory == stopped.output_directory
        assert not (stopped.output_directory / CHECKPOINT_FILENAME).exists()
        assert window.start_button.isEnabled()
        assert not window.simulation_mode.isEnabled()

        window.x_points.setValue(5)
        window.y_points.setValue(5)
        window.start_new()
        wait_until(app, lambda: not window.map_controller.busy)
        assert not errors
        assert results[-1].complete
        assert results[-1].output_directory != first
        np.testing.assert_array_equal(results[-1].counts, results[0].counts)
    finally:
        if window.map_controller.busy:
            window.request_stop()
            wait_until(app, lambda: not window.map_controller.busy, timeout=30)
        window.close()
