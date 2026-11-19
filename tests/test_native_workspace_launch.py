"""Native launch is real composition, but has no executable hardware route."""

import asyncio
import builtins
import json
import shutil
from pathlib import Path

import pytest

from labtools.runtime import native_workspace as native
from labtools.runtime.native_candidate import NativeExecutionDisabled

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "examples/workspace/working-lab"


@pytest.fixture(autouse=True)
def no_native_imports(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "u6", "serial", "pyvisa", "PyQt6")):
            raise AssertionError("Forbidden import during native headless launch: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.fixture
def manifest(tmp_path):
    shutil.copytree(BUNDLE, tmp_path / "bundle")
    return tmp_path / "bundle/candidate.json"


def test_launch_composes_existing_boundaries_and_one_authority(manifest):
    with native.NativeWorkspace(manifest) as workspace:
        assert workspace.services._map._ownership is workspace._ownership
        assert workspace.services._spectrum._ownership is workspace._ownership
        report = workspace.describe()
        assert report["workspace_kind"] == "native-candidate"
        assert report["inputs_complete"] and not report["execution_enabled"]
        assert not report["hardware_opened"] and not report["environment_probed"]
        assert report["configured_map"]["safe_voltage_min_v"] == -10
        assert report["configured_spectrum"]["preset"] == "syncerity"
        assert report["selection"]["labjack"]["physical_serial"] is None
        assert report["selection"]["monochromator"]["physical_identity"] is None
        assert report["selection"]["spectrometer"]["expected_serial_number"] == "Camera SN: 926"
        assert report["selection"]["counter"]["address"] == "169.254.99.159"
        assert report["selection"]["optical_path"]["resources"] == ["working-lab-optical-path"]
        assert not workspace._ownership.session.reservations()
    assert workspace._closed
    workspace.close()
    with pytest.raises(RuntimeError, match="closed"):
        workspace.describe()


def test_refusal_recovery_and_new_event_loops(manifest):
    for _ in range(2):
        with native.NativeWorkspace(manifest) as workspace:
            with pytest.raises(NativeExecutionDisabled):
                workspace.acquire_map(workspace.plan.map_config)
            for _ in range(2):
                with pytest.raises(NativeExecutionDisabled):
                    asyncio.run(workspace.acquire_spectrum())
                with pytest.raises(NativeExecutionDisabled):
                    asyncio.run(workspace.capture_dark())
            assert not workspace._ownership.session.reservations()


def test_cancellation_before_coroutine_start_never_opens_devices(manifest):
    async def cancel(workspace):
        task = asyncio.create_task(workspace.acquire_spectrum())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with native.NativeWorkspace(manifest) as workspace:
        asyncio.run(cancel(workspace))
        assert not workspace._ownership.session.reservations()
        assert workspace.describe()["execution_enabled"] is False


@pytest.mark.parametrize("call", [
    lambda: native._labjack(),
    lambda: native._counter("169.254.99.159"),
    lambda: native._mirror(None, dio_pin=2),
    lambda: native._gate(None, pin=0),
    lambda: native._spectrometer(preset="syncerity"),
])
def test_native_constructor_gate_precedes_even_importlib(monkeypatch, call):
    def forbidden(*args, **kwargs):
        pytest.fail("Gate allowed a native import")

    monkeypatch.setattr(native.importlib, "import_module", forbidden)
    with pytest.raises(NativeExecutionDisabled):
        call()


def test_source_edit_invalidates_window_refresh_and_operations(manifest):
    with native.NativeWorkspace(manifest) as workspace:
        path = manifest.parent / "profile.json"
        before = path.read_bytes()
        path.write_bytes(before + b"\n")
        with pytest.raises(ValueError, match="source changed"):
            workspace.describe()
        with pytest.raises(ValueError, match="source changed"):
            workspace.acquire_map(workspace.plan.map_config)
        path.write_bytes(before)
        assert workspace.describe()["inputs_complete"]


def test_missing_configuration_fails_before_ownership(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid input created a session")

    monkeypatch.setattr(native, "WorkspaceOwnership", forbidden)
    with pytest.raises(native.NativeWorkspaceInputError) as caught:
        native.NativeWorkspace(tmp_path / "missing.json")
    assert caught.value.report["input_errors"]


def test_failed_binding_closes_existing_authority(manifest, monkeypatch):
    instances = []
    original = native.WorkspaceOwnership

    def ownership(config):
        result = original(config)
        instances.append(result)
        return result

    def fail(**kwargs):
        raise RuntimeError("binding failure")

    monkeypatch.setattr(native, "WorkspaceOwnership", ownership)
    monkeypatch.setattr(native, "DisabledNativeCandidate", fail)
    with pytest.raises(RuntimeError, match="binding failure"):
        native.NativeWorkspace(manifest)
    assert len(instances) == 1
    with pytest.raises(RuntimeError):
        instances[0].reserve("Spectrum")


def test_cli_headless_closes_without_qt(manifest, capsys):
    from labtools.cli import main

    main(["workspace", "launch", str(manifest), "--headless"])
    report = json.loads(capsys.readouterr().out)
    assert report["workspace_kind"] == "native-candidate"
    assert not report["execution_enabled"]


@pytest.mark.parametrize("flag", ["--execute", "--enable", "--discover"])
def test_cli_has_no_gate_bypass(manifest, flag):
    from labtools.cli import main

    with pytest.raises(SystemExit) as caught:
        main(["workspace", "launch", str(manifest), "--headless", flag])
    assert caught.value.code == 2


def test_cli_invalid_input_is_structured_and_does_not_launch_qt(tmp_path, capsys):
    from labtools.cli import main

    with pytest.raises(SystemExit) as caught:
        main(["workspace", "launch", str(tmp_path / "missing.json")])
    assert caught.value.code == 2
    assert json.loads(capsys.readouterr().out)["input_errors"]


def test_gui_failure_closes_workspace(manifest, monkeypatch):
    from labtools.cli import main
    from labtools.gui import native_workspace as gui

    captured = []

    def fail(workspace):
        captured.append(workspace)
        raise ImportError("Qt runtime unavailable")

    monkeypatch.setattr(gui, "launch_window", fail)
    with pytest.raises(ImportError, match="Qt runtime"):
        main(["workspace", "launch", str(manifest)])
    assert captured[0]._closed


def test_source_change_before_context_entry_closes_session(manifest):
    workspace = native.NativeWorkspace(manifest)
    manifest.write_text("{}")
    with pytest.raises(ValueError, match="source changed"), workspace:
        pytest.fail("Changed source entered context")
    assert workspace._closed


def test_cli_explicit_simulation_is_not_native_gate_bypass(manifest, capsys):
    from labtools.cli import main

    main(["workspace", "launch", str(manifest), "--headless", "--simulate"])
    report = json.loads(capsys.readouterr().out)
    assert report["workspace_kind"] == "explicit-simulation"
    assert report["simulation_execution_enabled"] and report["synthetic"]
    assert not report["execution_enabled"] and not report["native_execution_enabled"]
    assert not report["hardware_opened"] and not report["environment_probed"]
    assert report["camera_preview"]["source"] == "simulation only"
    with native.NativeWorkspace(manifest) as workspace:
        with pytest.raises(NativeExecutionDisabled):
            workspace.acquire_map()
        with pytest.raises(NativeExecutionDisabled):
            workspace.acquire_anneal()
