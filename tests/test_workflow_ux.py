"""Baseline-first sequences, no-output operation and consolidated live Qt views."""

import json
from dataclasses import replace
from pathlib import Path
from threading import Event

import numpy as np
import pytest
from test_experiment_panels import spin
from test_experiment_workflows import cube, program

pytest_plugins = ["test_experiment_panels", "test_experiment_workflows"]

from labtools.runtime.experiment_workflows import run_sequence
from labtools.runtime.operator_spectrum import ensure_operator_spectrum


@pytest.mark.parametrize("measurement", ["Spectrum", "Intensity map", "Hyperspectral"])
def test_baseline_and_exact_one_pair_per_cycle_without_files(workspace, tmp_path, measurement):
    request = cube(workspace) if measurement == "Hyperspectral" else workspace.workflows.spectrum_settings() if measurement == "Spectrum" else replace(workspace.workflows.map_config(), x_points=2, y_points=2, integration_time_s=0.001)
    before = set(tmp_path.rglob('*'))
    displayed = []
    result = run_sequence(workspace, program(workspace), measurement, request, cycles=2, save_output=False,
                          output_root=tmp_path / "must-not-exist", display=lambda kind, value: displayed.append(kind))
    assert result["status"] == "completed"
    assert [s["phase"] for s in result["steps"]] == [measurement, "Annealing", measurement, "Annealing", measurement]
    assert [s["role"] for s in result["steps"]] == ["baseline", "anneal", "post-anneal", "anneal", "post-anneal"]
    assert result["steps"][0]["cycle"] == 0
    assert all(s["output"] is None for s in result["steps"])
    assert set(tmp_path.rglob('*')) == before
    assert displayed


def test_baseline_failure_prevents_any_anneal(workspace, tmp_path, monkeypatch):
    runtime = ensure_operator_spectrum(workspace)
    async def fail(*args, **kwargs):
        raise OSError("baseline failed")
    monkeypatch.setattr(runtime.facade, "acquire", fail)
    anneals = []
    monkeypatch.setattr(workspace, "acquire_anneal", lambda *a, **k: anneals.append(True))
    with pytest.raises(OSError, match="baseline"):
        run_sequence(workspace, program(workspace), "Spectrum", workspace.workflows.spectrum_settings(), cycles=2,
                     save_output=False)
    assert not anneals
    assert all(s.owner is None for s in workspace._ownership.status().resources)


def test_saved_baseline_has_distinct_folder_and_role(workspace, tmp_path):
    result = run_sequence(workspace, program(workspace), "Spectrum", workspace.workflows.spectrum_settings(), cycles=1,
                          output_root=tmp_path)
    baseline = Path(result["steps"][0]["output"])
    assert baseline.name == "0000-baseline" and (baseline / "spectrum.npz").exists()
    assert json.loads((baseline.parent / "sequence.json").read_text())["baseline_measurement"] is True


def test_one_visible_annealing_tab_and_shared_dwell(window):
    app, widget, _ = window
    names = [widget.tabs.tabText(i) for i in range(widget.tabs.count())]
    assert names.count("Annealing") == 1 and "Anneal programs" not in names and "Alignment" not in names
    program_panel = widget.pages["Anneal programs"]
    widget.tabs.setCurrentWidget(widget.pages["Annealing"])
    app.processEvents()
    assert program_panel.mode.isVisible()
    assert program_panel.first_dwell is widget.pages["Annealing"].dwell
    program_panel.mode.setCurrentText("Single point")
    widget.pages["Annealing"].start_button.click()
    spin(app, lambda: not program_panel.busy)
    assert program_panel.last_result["completed_points"] == 1


def test_cube_grid_is_independent_and_output_edges_match(window):
    app, widget, _ = window
    panel = widget.pages["Hyperspectral"]
    widget.tabs.setCurrentWidget(panel)
    panel.x_points.setValue(3)
    panel.y_points.setValue(4)
    panel.x_start.setValue(-0.3)
    panel.y_stop.setValue(0.4)
    config = panel.snapshot()
    assert config.x_points == 3 and config.y_points == 4
    assert widget.pages["Intensity map"].x_points.value() == 2
    app.processEvents()
    assert abs(panel.output.geometry().right() - panel.browse_button.geometry().right()) <= 1
    sequence = widget.pages["Sequences"]
    widget.tabs.setCurrentWidget(sequence)
    app.processEvents()
    assert abs(sequence.output.geometry().right() - sequence.browse_button.geometry().right()) <= 1
    assert not hasattr(sequence, "anneals") and not hasattr(sequence, "measurements")


def test_live_cube_visible_before_job_completion(window, monkeypatch):
    app, widget, _ = window
    panel = widget.pages["Hyperspectral"]
    from labtools.acquisition.hyperspectral import HyperspectralService
    original = HyperspectralService.acquire
    release = Event()
    async def blocked(self, config, **kwargs):
        callback = kwargs["pixel_callback"]
        def pixel(*args):
            callback(*args)
            assert release.wait(5)
        kwargs["pixel_callback"] = pixel
        return await original(self, config, **kwargs)
    monkeypatch.setattr(HyperspectralService, "acquire", blocked)
    panel.start()
    try:
        spin(app, lambda: panel.displayed_measurement is not None)
        assert panel.busy
        assert panel.displayed_measurement[0] == "cube-live"
        image = panel.displayed_measurement[1][0]
        assert np.isfinite(image).sum() == 1 and not image.flags.writeable
        assert len(panel.map_axes.images) == 1 and len(panel.spectrum_axes.lines) == 1
    finally:
        release.set()
        spin(app, lambda: not panel.busy)


def test_alignment_popup_close_reopen_and_shared_worker(window):
    app, widget, workspace = window
    popup = widget.alignment_window
    widget.open_alignment_button.click()
    assert popup.isWindow() and popup.isVisible()
    popup.start_alignment()
    spin(app, lambda: popup._sequence >= 1)
    popup.close()
    spin(app, lambda: not popup.isVisible())
    assert workspace._operator_spectrum.worker.is_alive()
    widget.open_alignment_button.click()
    popup.start_alignment()
    spin(app, lambda: popup._sequence >= 1)
    widget.stop_all()
    spin(app, lambda: not widget.any_busy())


@pytest.mark.parametrize("measurement", ["Spectrum", "Intensity map", "Hyperspectral"])
def test_sequence_displays_latest_measurement_and_optional_output(window, measurement):
    app, widget, _ = window
    panel = widget.pages["Sequences"]
    panel.measurement.setCurrentText(measurement)
    panel.save_output.setChecked(False)
    panel.output.clear()
    panel.start()
    spin(app, lambda: not panel.busy)
    assert panel.last_result["status"] == "completed"
    assert len(panel.last_result["steps"]) == 3
    assert panel.displayed_measurement is not None
    assert panel.spectrum_axes.lines if measurement == "Spectrum" else panel.map_axes.images
