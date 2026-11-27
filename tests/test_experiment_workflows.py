"""Point schedules, batch exclusion and simulated experiment data paths."""

import shutil
from dataclasses import replace
from pathlib import Path
from threading import Event

import numpy as np
import pytest

from labtools.config.anneal_program import AnnealProgram
from labtools.config.anneal_types import LaserAnnealConfig
from labtools.config.hyperspectral import HyperspectralConfig
from labtools.runtime.experiment_workflows import run_cube, run_program, run_sequence
from labtools.runtime.operator_spectrum import ensure_operator_spectrum
from labtools.runtime.session import ResourceBusyError
from labtools.runtime.workflow_batch import Batch, has_owner
from labtools.simulation.operator_session import SimulatedOperatorSession

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("spacing, expected", [("Linear", [1, 4, 7, 10]), ("Logarithmic", [1, 10, 100, 1000])])
def test_endpoint_spacing_and_serpentine_traversal(spacing, expected):
    base = LaserAnnealConfig(x_points=2, y_points=2, passes=2, point_dwell_s=expected[0], serpentine=True)
    points = AnnealProgram(base, "Dwell ramp array", expected[-1], spacing).points()
    np.testing.assert_allclose([p.point_dwell_s for p in points], expected * 2)
    assert [(p.x_start_v, p.y_start_v) for p in points[:4]] == [(-1, 1), (1, 1), (1, 3), (-1, 3)]


@pytest.mark.parametrize("first,last,spacing", [(0, 1, "Logarithmic"), (1, 0, "Logarithmic"), (-1, 1, "Linear"), (1, float("nan"), "Linear")])
def test_invalid_endpoints_are_rejected(first, last, spacing):
    with pytest.raises(ValueError):
        AnnealProgram(LaserAnnealConfig(point_dwell_s=first), "Dwell ramp array", last, spacing).points()


def test_single_point_and_descending_ramp():
    points = AnnealProgram(LaserAnnealConfig(passes=3), "Single point").points()
    assert len(points) == 3 and all(p.x_points == p.y_points == 1 for p in points)
    base = LaserAnnealConfig(x_points=3, y_points=1, point_dwell_s=100)
    np.testing.assert_allclose([p.point_dwell_s for p in AnnealProgram(base, "Dwell ramp array", 1, "Logarithmic").points()], [100, 10, 1])


def test_total_budget_and_one_point_ramp():
    with pytest.raises(ValueError):
        AnnealProgram(LaserAnnealConfig(maximum_open_time_s=0.1), "Dwell ramp array", 1).points()
    with pytest.raises(ValueError):
        AnnealProgram(LaserAnnealConfig(x_points=1, y_points=1), "Dwell ramp array", 1).points()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    with SimulatedOperatorSession(tmp_path / "bundle/candidate.json", preferences_path=tmp_path / "prefs.json", output_root=tmp_path, realtime=False) as workspace:
        ensure_operator_spectrum(workspace)
        yield workspace


def program(workspace):
    return AnnealProgram(replace(workspace.drafts.values["anneal"], x_points=1, y_points=1, passes=1, point_dwell_s=0.001), "Single point")


def cube(workspace):
    return HyperspectralConfig(workspace.plan.configuration_id, workspace.workflows.spectrum_settings(), -0.1, 0.1, 2, -0.1, 0.1, 2,
                               backend="simulation")


def test_batch_context_is_explicit_and_does_not_authorize_other_callers(workspace):
    batch = Batch(workspace._ownership, ("Spectrum", "Intensity map", "Annealing"))
    try:
        assert not has_owner(workspace._ownership, "Spectrum")
        with batch.borrow("Spectrum"), batch.borrow("Intensity map"):
            assert has_owner(workspace._ownership, "Spectrum") and has_owner(workspace._ownership, "Intensity map")
            assert not has_owner(workspace._ownership, "Annealing")
        for owner in ("Spectrum", "Intensity map", "Annealing"):
            with pytest.raises(ResourceBusyError):
                workspace._ownership.reserve(owner)
    finally:
        batch.release()


def test_program_executes_doses_and_writes_manifest(workspace, tmp_path):
    batch = Batch(workspace._ownership, ("Annealing",))
    try:
        with batch.borrow("Annealing"):
            result = run_program(workspace, program(workspace), output=tmp_path)
        assert result["status"] == "completed" and result["completed_points"] == 1
        assert (tmp_path / "program.json").exists()
    finally:
        batch.release()


def test_cube_uses_shared_worker_and_saves_result(workspace, tmp_path):
    batch = Batch(workspace._ownership, ("Spectrum", "Intensity map"))
    try:
        with batch.borrow("Spectrum"), batch.borrow("Intensity map"):
            result = run_cube(workspace, cube(workspace), output_path=tmp_path / "cube.npz")
        assert result.status == "complete" and result.completed_points == 4
        assert result.intensity.shape[:2] == (2, 2)
        assert (tmp_path / "cube.npz").exists()
        assert workspace._operator_spectrum.worker.status().state == "available"
    finally:
        batch.release()


@pytest.mark.parametrize("measurement", ["Spectrum", "Intensity map", "Hyperspectral"])
def test_sequence_all_measurements_order_repeats_and_outputs(workspace, tmp_path, measurement):
    request = cube(workspace) if measurement == "Hyperspectral" else workspace.workflows.spectrum_settings() if measurement == "Spectrum" else replace(workspace.workflows.map_config(), x_points=2, y_points=2, integration_time_s=0.001)
    result = run_sequence(workspace, program(workspace), measurement, request, cycles=2, output_root=tmp_path)
    assert result["status"] == "completed"
    assert [s["phase"] for s in result["steps"]] == [measurement] + ["Annealing", measurement] * 2
    assert all(state.owner is None for state in workspace._ownership.status().resources)


def test_cancelled_sequence_stops_before_measurement_and_releases(workspace, tmp_path):
    stop = Event()
    def report(text):
        if "Annealing point" in text:
            stop.set()
    result = run_sequence(workspace, program(workspace), "Spectrum", workspace.workflows.spectrum_settings(),
                          cycles=2, output_root=tmp_path, stop=stop, report=report)
    assert result["status"] == "cancelled"
    assert [s["phase"] for s in result["steps"]] == ["Spectrum", "Annealing"]
    assert all(state.owner is None for state in workspace._ownership.status().resources)


def test_program_failure_never_starts_measurement_and_releases_batch(workspace, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("shutter close failed")
    monkeypatch.setattr(workspace, "acquire_anneal", fail)
    with pytest.raises(OSError, match="shutter close"):
        run_sequence(workspace, program(workspace), "Spectrum", workspace.workflows.spectrum_settings(),
                     cycles=2, output_root=tmp_path)
    assert workspace._operator_spectrum.worker.status().state == "available"
    assert all(state.owner is None for state in workspace._ownership.status().resources)
    import json
    journal = next(tmp_path.glob("sequence-*/sequence.json"))
    assert json.loads(journal.read_text())["status"] == "failed"


def test_cube_cancel_preserves_partial_archive_and_allows_restart(workspace, tmp_path):
    stop = Event()
    batch = Batch(workspace._ownership, ("Spectrum", "Intensity map"))
    try:
        def progress(event):
            if event.completed_points >= 1:
                stop.set()
        with batch.borrow("Spectrum"), batch.borrow("Intensity map"):
            result = run_cube(workspace, cube(workspace), stop=stop, progress=progress, output_path=tmp_path / "partial.npz")
        assert result.status == "cancelled" and result.completed_points < 4
        assert (tmp_path / "partial.npz").exists()
        assert workspace._operator_spectrum.worker.status().state == "available"
    finally:
        batch.release()


def test_batch_context_does_not_authorize_an_unrelated_thread(workspace):
    from concurrent.futures import ThreadPoolExecutor
    batch = Batch(workspace._ownership, ("Spectrum",))
    try:
        with batch.borrow("Spectrum"), ThreadPoolExecutor(max_workers=1) as executor:
            assert has_owner(workspace._ownership, "Spectrum")
            assert not executor.submit(has_owner, workspace._ownership, "Spectrum").result(2)
    finally:
        batch.release()


@pytest.mark.parametrize("dark_mode", ["none", "once_per_map"])
def test_real_cube_uses_one_horiba_session_and_homes_mirror(tmp_path, monkeypatch, dark_mode):
    import json
    from dataclasses import asdict

    from labtools.config.anneal_workspace import InstrumentProfile
    from labtools.config.native_candidate import preflight_candidate
    from labtools.runtime.hardware_workspace import HardwareWorkspace
    from labtools.simulation.transport_fakes import (
        TransportTrace,
        map_factories,
        spectrum_factory,
    )

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    manifest = tmp_path / "bundle/candidate.json"
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(asdict(InstrumentProfile(profile_id="test", approved=True))))
    plan = preflight_candidate(manifest).plan
    trace = TransportTrace()
    with HardwareWorkspace(manifest, anneal_profile=profile, preferences_path=tmp_path / "p.json",
                           map_factories=map_factories(plan.map_config, trace),
                           spectrometer_factory=spectrum_factory(plan.spectrum_request.settings, trace),
                           stitcher=lambda captures, start, end: (np.array(captures[0][0]), np.array(captures[0][1][0]))) as workspace:
        config = replace(cube(workspace), backend="real", dark_mode=dark_mode)
        batch = Batch(workspace._ownership, ("Spectrum", "Intensity map"))
        try:
            with batch.borrow("Spectrum"), batch.borrow("Intensity map"):
                result = run_cube(workspace, config, output_path=tmp_path / "real-contract.npz")
            assert result.completed_points == 4
            if dark_mode == "once_per_map":
                from labtools.io.spectrum_records import load_dark_record

                dark = load_dark_record(tmp_path / "dark.npz")
                assert dark.segments and result.provenance.dark_record_id == dark.record_id
                assert result.provenance.reusable_dark_stage == "pre_stitch"
            events = trace.events()
            assert sum(e["resource"] == "spectrometer" and e["action"] == "connect" for e in events) == 1
            assert sum(e["resource"] == "mirror" and e["action"] == "move" for e in events) == 5
            assert len({e["thread"] for e in events}) == 1
        finally:
            batch.release()


def test_cube_workflow_saves_matching_dark_and_all_live_rows(workspace, tmp_path):
    from labtools.io.spectrum_records import load_dark_record

    batch = Batch(workspace._ownership, ("Spectrum", "Intensity map"))
    frames, darks = [], []
    try:
        with batch.borrow("Spectrum"), batch.borrow("Intensity map"):
            request = replace(cube(workspace), dark_mode="once_per_map")
            result = run_cube(workspace, request, output_path=tmp_path / "cube.npz",
                display=lambda kind, value: frames.append((kind, value)), on_dark=darks.append)
    finally:
        batch.release()
    record = load_dark_record(tmp_path / "dark.npz")
    assert record.record_id == darks[0].record_id == result.provenance.dark_record_id
    assert len(darks) == 1 and len(frames) == result.completed_points
    live = frames[-1][1][-1]
    for iy, ix in np.argwhere(result.completed_mask):
        x, y = live.get(iy, ix)
        np.testing.assert_array_equal(x, result.wavelength_nm)
        np.testing.assert_array_equal(y, result.intensity[iy, ix])
