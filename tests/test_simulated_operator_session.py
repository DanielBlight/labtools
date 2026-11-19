"""Source-backed whole-workspace simulation: no hardware imports, native gate intact."""

import asyncio
import builtins
import csv
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event

import numpy as np
import pytest

from labtools.runtime.native_candidate import NativeExecutionDisabled
from labtools.runtime.native_workspace import NativeWorkspace
from labtools.runtime.session import ResourceBusyError
from labtools.simulation.operator_session import SimulatedOperatorSession

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_hardware(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "pylablib", "u6", "serial", "pyvisa", "PyQt6")):
            raise AssertionError("Simulation attempted native/GUI import: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.fixture
def manifest(tmp_path):
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    return tmp_path / "bundle/candidate.json"


def test_explicit_mode_report_source_unchanged_and_native_gate(manifest, tmp_path):
    before = {path: path.read_bytes() for path in manifest.parent.iterdir()}
    with SimulatedOperatorSession(manifest, output_root=tmp_path / "synthetic") as session:
        report = session.describe()
        assert report["synthetic"] and report["simulation_execution_enabled"]
        assert not report["execution_enabled"] and not report["native_execution_enabled"]
        assert not report["hardware_opened"] and not report["environment_probed"]
        assert session.drafts.values["map"].backend == session.drafts.values["spectrum"].backend == "simulation"
        assert session.drafts.values["map"].safe_voltage_min_v == -10
        assert session.drafts.values["map"].safe_voltage_max_v == 10
        assert not session.drafts.values["map"].simulation_realtime
        assert session.workflow_preview()["simulation_execution_enabled"]
        with pytest.raises(RuntimeError, match="physical camera"):
            session.reserve_camera()
    with NativeWorkspace(manifest) as native:
        assert not native.describe()["execution_enabled"]
        with pytest.raises(NativeExecutionDisabled):
            native.acquire_map()
        with pytest.raises(NativeExecutionDisabled):
            native.acquire_anneal()
        with pytest.raises(NativeExecutionDisabled):
            asyncio.run(native.acquire_spectrum())
    assert all(path.read_bytes() == data for path, data in before.items())


def test_existing_map_and_spectrum_backends_end_to_end(manifest, tmp_path):
    with SimulatedOperatorSession(manifest, output_root=tmp_path / "synthetic") as session:
        config = replace(session.drafts.values["map"], x_points=3, y_points=2, integration_time_s=.01,
                         settle_time_s=0, save_results=False)
        with pytest.raises(PermissionError):
            session.acquire_map(config)
        with session._ownership.reserve("Intensity map"), ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(session.acquire_map, config).result()
        assert result.complete and result.completed_mask.sum() == 6
        assert np.isfinite(result.counts).all()
        settings = session.drafts.values["spectrum"]

        async def spectrum():
            with session._ownership.reserve("Spectrum"):
                dark = await session.capture_dark(settings)
                raw = await session.acquire_spectrum(settings)
                corrected = await session.acquire_spectrum(settings, dark_mode="pre_taken", dark=dark)
                assert raw.settings.backend == corrected.settings.backend == "simulation"
                assert np.allclose(raw.intensity - corrected.intensity, dark.intensity)
                assert len(corrected.wavelength_nm) == 64
                with pytest.raises(ValueError):
                    await session.acquire_spectrum(replace(settings, backend="real"))

        asyncio.run(spectrum())
        events = session.simulated_services.events()
        assert any(event["resource"] == "counter" for event in events)
        assert any(event["resource"] == "detector" for event in events)
        assert not session._ownership.session.reservations()


def test_anneal_progress_synthetic_logs_and_cleanup(manifest, tmp_path):
    with SimulatedOperatorSession(manifest, output_root=tmp_path / "synthetic") as session:
        config = replace(session.drafts.values["anneal"], x_points=3, y_points=2, passes=2,
                         serpentine=True, gui_update_interval_s=0)
        progress, status = [], []
        with pytest.raises(PermissionError):
            session.acquire_anneal(config)
        with session._ownership.reserve("Annealing"):
            result = session.acquire_anneal(config, progress_callback=progress.append, status_callback=status.append)
        assert result.completed and not result.stopped and result.completed_points == 12
        assert len(progress) == 12
        assert [point.x_index for point in progress[:6]] == [0, 1, 2, 2, 1, 0]
        state = session.anneal_simulator.snapshot()
        assert state["shutter"] == "closed" and not state["running"]
        assert state["stage_coordinate"] == config.return_rotation_coordinate
        assert (state["mirror_x_v"], state["mirror_y_v"]) == (config.home_x_voltage_v, config.home_y_voltage_v)
        assert all(message.startswith("SIMULATED:") for message in status)
        metadata = json.loads((result.output_directory / "metadata.json").read_text())
        assert metadata["synthetic"] and metadata["backend"] == "simulation"
        rows = list(csv.DictReader((result.output_directory / "positions.csv").open()))
        assert len(rows) == 12 and all(row["backend"] == "simulation" for row in rows)
        assert json.loads((result.output_directory / "result.json").read_text())["error"] is None


@pytest.mark.parametrize("kind", ["stop", "callback_failure", "pre_cancel"])
def test_anneal_cancellation_failure_cleanup_and_reuse(manifest, tmp_path, kind):
    with SimulatedOperatorSession(manifest, output_root=tmp_path / "synthetic") as session:
        config = replace(session.drafts.values["anneal"], x_points=4, y_points=3,
                         gui_update_interval_s=0, save_run_log=False)
        stop = Event()
        if kind == "pre_cancel":
            stop.set()

        def progress(update):
            if kind == "callback_failure":
                raise RuntimeError("test progress failure")
            stop.set()

        with session._ownership.reserve("Annealing"):
            if kind == "callback_failure":
                with pytest.raises(RuntimeError, match="test progress failure"):
                    session.acquire_anneal(config, stop_event=stop, progress_callback=progress)
            else:
                result = session.acquire_anneal(config, stop_event=stop, progress_callback=progress)
                assert result.stopped and not result.completed
                assert result.completed_points == (0 if kind == "pre_cancel" else 1)
        assert session.anneal_simulator.snapshot()["shutter"] == "closed"
        assert not session.anneal_simulator.snapshot()["running"]
        with session._ownership.reserve("Annealing"):
            assert session.acquire_anneal(config).completed


@pytest.mark.parametrize("owner", ["Intensity map", "Spectrum", "Annealing"])
def test_one_existing_authority_excludes_conflicts(manifest, owner):
    with SimulatedOperatorSession(manifest) as session, session._ownership.reserve(owner):
        for other in {"Intensity map", "Spectrum", "Annealing"} - {owner}:
            with pytest.raises(ResourceBusyError):
                session._ownership.reserve(other)


def test_simulation_preferences_are_separate_and_roundtrip(manifest, tmp_path):
    with NativeWorkspace(manifest) as native:
        native.save_preferences(map=replace(native.plan.map_config, x_points=9))
        native_path = native.drafts.store.path
        native_bytes = native_path.read_bytes()
    with SimulatedOperatorSession(manifest, output_root=tmp_path / "synthetic") as session:
        sim_path = session.drafts.store.path
        assert sim_path != native_path
        assert session.drafts.values["map"].x_points == 40
        session.save_preferences(map=replace(session.drafts.values["map"], x_points=7),
                                 anneal=replace(session.drafts.values["anneal"], passes=3))
    with SimulatedOperatorSession(manifest) as session:
        assert session.drafts.values["map"].x_points == 7
        assert session.drafts.values["map"].backend == "simulation"
        assert session.drafts.values["anneal"].passes == 3
        assert session.drafts.values["map"].output_root == tmp_path / "synthetic/Maps"
    assert native_path.read_bytes() == native_bytes
    with NativeWorkspace(manifest) as native:
        assert native.drafts.values["map"].x_points == 9
        assert native.drafts.values["map"].backend == "real"


def test_corrupt_simulation_preferences_never_restore_native_output_roots(manifest, tmp_path):
    prefs = tmp_path / "prefs.json"
    prefs.write_text("broken")
    with SimulatedOperatorSession(manifest, output_root=tmp_path / "synthetic", preferences_path=prefs) as session:
        assert session.drafts.values["map"].output_root == tmp_path / "synthetic/Maps"
        assert session.drafts.values["anneal"].output_root == tmp_path / "synthetic/Annealing"


def test_source_limits_and_real_settings_refused(manifest):
    with SimulatedOperatorSession(manifest) as session:
        with pytest.raises(ValueError):
            session.workflows.map_config(replace(session.drafts.values["map"], x_start_v=-11))
        with pytest.raises(ValueError):
            session.workflows.map_config(replace(session.drafts.values["map"], backend="real"))
        with pytest.raises(ValueError):
            session.drafts.validate("anneal", replace(session.drafts.values["anneal"], maximum_mirror_voltage_v=20))
        with pytest.raises(ValueError):
            session.workflows.spectrum_settings(replace(session.drafts.values["spectrum"], backend="real"))
    with pytest.raises(RuntimeError, match="closed"):
        session.acquire_map()


def test_saved_map_metadata_is_explicitly_synthetic(manifest, tmp_path):
    with SimulatedOperatorSession(manifest, output_root=tmp_path / "synthetic") as session:
        config = replace(session.drafts.values["map"], x_points=2, y_points=2, integration_time_s=.01,
                         settle_time_s=0, save_results=True)
        with session._ownership.reserve("Intensity map"):
            result = session.acquire_map(config)
        metadata = json.loads((result.output_directory / "intensity_map_metadata.json").read_text())
        assert metadata["backend"] == "simulation"
        assert result.output_directory.is_relative_to(tmp_path / "synthetic/Maps")


def test_explicit_output_override_and_realtime_do_not_mutate_source(manifest, tmp_path):
    with SimulatedOperatorSession(manifest, output_root=tmp_path / "first") as session:
        session.save_preferences()
    with SimulatedOperatorSession(manifest, output_root=tmp_path / "second", realtime=True) as session:
        assert session.drafts.values["map"].simulation_realtime
        assert session.drafts.values["map"].output_root == tmp_path / "second/Maps"
        assert session.drafts.display["spectrum_output"] == str(tmp_path / "second/Spectra")
        assert session.plan.map_config.backend == "real"  # Source provenance, not active backend.
        assert session.plan.map_config.simulation_realtime
