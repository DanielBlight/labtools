"""Source-backed operator drafts and gated worker/service bindings, no native I/O."""

import asyncio
import builtins
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import get_ident

import pytest

from labtools.runtime.native_candidate import NativeExecutionDisabled
from labtools.runtime.native_workspace import NativeWorkspace

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "u6", "serial", "pyvisa", "PyQt6")):
            raise AssertionError("Forbidden native/GUI import: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.fixture
def workspace(tmp_path):
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    with NativeWorkspace(tmp_path / "bundle/candidate.json") as workspace:
        yield workspace


def test_exact_source_defaults_and_preview_no_writes(workspace):
    before = {source.path: source.path.read_bytes() for source in workspace.plan.sources}
    preview = workspace.workflow_preview()
    assert preview["map"]["x_points"] == 40
    assert preview["map"]["safe_voltage_min_v"] == -10
    assert preview["spectrum"]["gain"] == 2
    assert preview["spectrum"]["exposure_s"] == .5
    assert preview["draft_only"] and not preview["execution_enabled"]
    assert preview["map"]["backend"] == preview["spectrum"]["backend"] == "real"
    assert not workspace._ownership.session.reservations()
    assert all(path.read_bytes() == data for path, data in before.items())
    assert workspace.describe()["operator_workflows_bound"]


def test_edits_are_drafts_and_expectations_not_readbacks(workspace):
    mapping = replace(workspace.plan.map_config, x_points=7, y_points=8, integration_time_s=.02)
    settings = replace(workspace.plan.spectrum_request.settings, preset="symphony", exposure_s=.1)
    preview = workspace.workflow_preview(mapping, settings)
    assert preview["map"]["x_points"] == 7
    assert preview["spectrum"]["preset"] == "symphony"
    assert preview["detector_expectations_not_readbacks"]["expected_serial_number"] == "Camera SN: 26070"
    preview["detector_expectations_not_readbacks"]["expected_serial_number"] = "changed"
    assert workspace.plan.hardware_settings["detectors"]["symphony"]["expected_serial_number"] == "Camera SN: 26070"
    assert workspace.plan.map_config.x_points == 40
    assert workspace.plan.spectrum_request.settings.preset == "syncerity"


@pytest.mark.parametrize("changes", [
    {"backend": "simulation"}, {"time_controller_address": "other"},
    {"mirror_dio_pin": 4}, {"spad_gate_pin": 1},
    {"safe_voltage_min_v": -11}, {"safe_voltage_max_v": 9},
    {"x_start_v": -11}, {"integration_time_s": 0}, {"x_points": 1},
])
def test_map_hardware_and_envelope_source_bound(workspace, changes):
    with pytest.raises(ValueError):
        workspace.workflow_preview(replace(workspace.plan.map_config, **changes))


@pytest.mark.parametrize("changes", [
    {"backend": "simulation"}, {"configuration_id": "other"}, {"gain": 99},
    {"speed": 99}, {"exposure_s": .02}, {"preset": "symphony", "exposure_s": .065},
    {"start_nm": 900, "end_nm": 600}, {"combine_mode": "single", "n_frames": 3},
])
def test_spectrum_source_options_validated(workspace, changes):
    with pytest.raises(ValueError):
        workspace.workflow_preview(spectrum=replace(workspace.plan.spectrum_request.settings, **changes))


def test_type_refusal_and_source_edit(workspace):
    with pytest.raises(TypeError):
        workspace.workflow_preview(mapping={})
    with pytest.raises(TypeError):
        workspace.workflow_preview(spectrum={})
    path = workspace.manifest.parent / "profile.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source changed"):
        workspace.workflow_preview()


def test_bound_map_callable_refuses_on_worker_without_output_or_lease_leak(workspace, tmp_path):
    config = replace(workspace.plan.map_config, output_root=tmp_path / "must-not-exist")
    caller = get_ident()

    def run():
        assert get_ident() != caller
        with pytest.raises(NativeExecutionDisabled):
            workspace.acquire_map(config)

    for _ in range(2):
        with workspace._ownership.reserve("Intensity map"):
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(run).result()
            states = workspace._ownership.status().resources
            assert all(resource.owner == "Intensity map" for resource in states
                       if resource.name in workspace.plan.reservation_config.map_resources)
        assert not workspace._ownership.session.reservations()
    assert not config.output_root.exists()


def test_bound_spectrum_service_refuses_acquire_dark_and_connection_on_worker_loops(workspace):
    settings = workspace.plan.spectrum_request.settings
    service = workspace.spectrum_service

    async def run():
        for operation in (service.acquire, service.capture_dark, service.test_connection):
            with pytest.raises(NativeExecutionDisabled):
                await operation(settings)

    for _ in range(2):
        with (
            workspace._ownership.reserve("Spectrum"),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            executor.submit(lambda: asyncio.run(run())).result()
        assert not workspace._ownership.session.reservations()


def test_cancel_before_backend_then_refusal_recovery(workspace):
    async def run():
        task = asyncio.create_task(workspace.acquire_spectrum())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(NativeExecutionDisabled):
            await workspace.capture_dark()

    asyncio.run(run())
    assert not workspace._ownership.session.reservations()


def test_closed_workspace_refuses_retained_service(workspace):
    settings = workspace.plan.spectrum_request.settings
    service = workspace.spectrum_service
    workspace.close()
    with pytest.raises(RuntimeError, match="closed"):
        asyncio.run(service.acquire(settings))


def test_headless_report_retains_implicit_selection_and_gate(workspace):
    report = workspace.describe()
    assert report["selection"]["labjack"]["physical_serial"] is None
    assert report["selection"]["monochromator"]["physical_identity"] is None
    assert not report["execution_enabled"]
    json.dumps(workspace.workflow_preview())
