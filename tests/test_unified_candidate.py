"""Unified native candidate: persistence, three-way exclusion, no hardware."""

import asyncio
import builtins
import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from labtools.config.anneal_workspace import InstrumentProfile
from labtools.runtime.native_candidate import NativeExecutionDisabled
from labtools.runtime.native_workspace import NativeWorkspace
from labtools.runtime.session import ResourceBusyError
from labtools.runtime.workspace_preferences import WorkspacePreferences

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_native(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "u6", "serial", "pyvisa", "PyQt6")):
            raise AssertionError("Native/Qt import in unified candidate: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.fixture
def inputs(tmp_path):
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    return tmp_path / "bundle/candidate.json", tmp_path / "prefs.json"


def test_three_workflow_defaults_and_gate(inputs):
    manifest, prefs = inputs
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        report = workspace.describe()
        assert report["workflows"] == ["Intensity map", "Spectrum", "Annealing"]
        assert not report["execution_enabled"] and not report["hardware_opened"]
        assert report["anneal"]["physical_shutter_stage_camera"].startswith("not probed")
        config = workspace.drafts.values["anneal"]
        assert (config.minimum_mirror_voltage_v, config.maximum_mirror_voltage_v) == (-10, 10)
        assert config.mirror_dio_pin == workspace.plan.map_config.mirror_dio_pin
        with pytest.raises(NativeExecutionDisabled):
            workspace.acquire_anneal(config)
        with pytest.raises(NativeExecutionDisabled):
            workspace.acquire_map()
        with pytest.raises(NativeExecutionDisabled):
            asyncio.run(workspace.acquire_spectrum())
        assert not prefs.exists()


@pytest.mark.parametrize("first,second", [
    ("Annealing", "Intensity map"), ("Annealing", "Spectrum"),
    ("Intensity map", "Annealing"), ("Spectrum", "Annealing"),
    ("Intensity map", "Spectrum"), ("Spectrum", "Intensity map"),
])
def test_cross_workflow_exclusion_release_and_reuse(inputs, first, second):
    manifest, prefs = inputs
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        authority = workspace._ownership
        with authority.reserve(first):
            with pytest.raises(ResourceBusyError):
                authority.reserve(second)
            with pytest.raises(NativeExecutionDisabled):
                workspace.acquire_anneal()
            assert any(resource.owner == first for resource in authority.status().resources)
        with authority.reserve(second):
            assert any(resource.owner == second for resource in authority.status().resources)
        assert not authority.session.reservations()
        assert workspace.services._map._ownership is workspace.services._spectrum._ownership is authority


def test_all_preferences_round_trip_no_source_or_hardware_state(inputs):
    manifest, prefs = inputs
    before = {path: path.read_bytes() for path in manifest.parent.iterdir()}
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        mapping = replace(workspace.plan.map_config, x_points=9, y_points=11, integration_time_s=.25)
        spectrum = replace(workspace.plan.spectrum_request.settings, preset="symphony", exposure_s=.2)
        anneal = replace(workspace.drafts.anneal_base, passes=3, point_dwell_s=.002)
        workspace.save_preferences(map=mapping, spectrum=spectrum, anneal=anneal,
                                   display={"map_log": True, "spectrum_output": "C:/LabData/Spectra", "spectrum_csv": True})
    raw = json.loads(prefs.read_text())
    assert set(raw["workflows"]) == {"map", "spectrum", "anneal", "display"}
    assert not {"backend", "time_controller_address", "mirror_dio_pin", "safe_voltage_min_v"} & set(raw["workflows"]["map"])
    assert not {"sc10_port", "minimum_mirror_voltage_v", "instrument_profile_id"} & set(raw["workflows"]["anneal"])
    assert all(path.read_bytes() == data for path, data in before.items())
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        assert workspace.drafts.values["map"] == mapping
        assert workspace.drafts.values["spectrum"] == spectrum
        assert workspace.drafts.values["anneal"] == anneal
        assert workspace.drafts.display["map_log"] is True
        assert not workspace._ownership.session.reservations()
        assert not workspace.describe()["execution_enabled"]


@pytest.mark.parametrize("workflow,field,value", [
    ("map", "x_points", 0), ("map", "x_points", True), ("map", "x_points", 1.5),
    ("map", "integration_time_s", float("nan")), ("map", "time_controller_address", "other"),
    ("map", "safe_voltage_min_v", -20), ("map", "channels", [True]),
    ("spectrum", "gain", 99), ("spectrum", "backend", "simulation"),
    ("spectrum", "exposure_s", .001), ("spectrum", "configuration_id", "other"),
    ("anneal", "passes", 0), ("anneal", "return_rotation_stage", "false"),
    ("anneal", "sc10_port", "COM99"), ("anneal", "maximum_open_time_s", 999999),
    ("anneal", "x_start_v", -11), ("anneal", "point_dwell_s", float("inf")),
    ("display", "laser_on", True), ("display", "camera_gain", -1),
])
def test_corrupt_or_unsafe_saved_values_rejected_per_workflow(inputs, workflow, field, value):
    manifest, prefs = inputs
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        workspace.save_preferences()
        baseline = workspace.drafts.values.get(workflow)
    raw = json.loads(prefs.read_text())
    raw["workflows"][workflow][field] = value
    prefs.write_text(json.dumps(raw))
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        if workflow == "display":
            assert workspace.drafts.display == {}
        else:
            assert workspace.drafts.values[workflow] == baseline
        assert workspace.drafts.store.messages
        assert not workspace.describe()["execution_enabled"]


def test_source_change_discards_stale_preferences(inputs):
    manifest, prefs = inputs
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        workspace.save_preferences(map=replace(workspace.plan.map_config, x_points=17))
    path = manifest.parent / "map.json"
    data = json.loads(path.read_text())
    data["recipe"]["config"]["x_points"] = 12
    path.write_text(json.dumps(data))
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        assert workspace.drafts.values["map"].x_points == 12
        assert workspace.drafts.store.messages


def test_invalid_json_and_atomic_failure_preserve_old_file(inputs, monkeypatch):
    manifest, prefs = inputs
    prefs.write_text("broken")
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        assert workspace.drafts.store.messages
        workspace.save_preferences()
        old = prefs.read_bytes()
        from labtools.runtime import workspace_preferences

        def fail(*args):
            raise OSError("disk unavailable")

        monkeypatch.setattr(workspace_preferences.os, "replace", fail)
        with pytest.raises(OSError, match="disk unavailable"):
            workspace.save_preferences(map=replace(workspace.plan.map_config, x_points=8))
        assert prefs.read_bytes() == old
        assert list(prefs.parent.glob(prefs.name + ".*")) == []


def test_existing_local_limits_and_stage_policy_are_respected(inputs, tmp_path):
    manifest, prefs = inputs
    local = replace(InstrumentProfile(), approved=True, profile_id="test-only", minimum_mirror_voltage_v=-2,
                    maximum_mirror_voltage_v=2, maximum_open_time_s=10)
    path = tmp_path / "local-profile.json"
    path.write_text(json.dumps(asdict(local)))
    before = path.read_bytes()
    with NativeWorkspace(manifest, preferences_path=prefs, anneal_profile=path) as workspace:
        baseline = workspace.drafts.anneal_base
        assert (baseline.minimum_mirror_voltage_v, baseline.maximum_mirror_voltage_v) == (-2, 2)
        for changes in ({"x_start_v": -3}, {"maximum_open_time_s": 11}, {"return_rotation_stage": False},
                        {"anneal_rotation_coordinate": 1}):
            with pytest.raises(ValueError):
                workspace.drafts.validate("anneal", replace(baseline, **changes))
        valid = replace(baseline, y_stop_v=2, output_root=tmp_path)
        assert workspace.drafts.validate("anneal", valid) == valid
        path.write_bytes(before + b"\n")
        with pytest.raises(ValueError, match="source changed"):
            workspace.acquire_anneal(valid)
    assert path.read_bytes() == before + b"\n"


def test_missing_explicit_profile_reports_error_without_blocking_other_tabs(inputs, tmp_path):
    manifest, prefs = inputs
    with NativeWorkspace(manifest, preferences_path=prefs, anneal_profile=tmp_path / "missing.json") as workspace:
        assert workspace.describe()["anneal"]["profile_error"]
        with pytest.raises(ValueError, match="profile"):
            workspace.acquire_anneal()
        assert workspace.workflow_preview()["draft_only"]


def test_configuration_specific_preferences_namespace(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    first = WorkspacePreferences("first", "fingerprint")
    second = WorkspacePreferences("second", "fingerprint")
    assert first.path != second.path
    first.write({})
    assert not second.path.exists()


def test_float_widget_values_restore_against_integer_json_defaults(inputs):
    manifest, prefs = inputs
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        config = replace(workspace.plan.map_config, x_start_v=-1.5, x_stop_v=1.5,
                         y_start_v=-1.25, y_stop_v=1.25)
        workspace.save_preferences(map=config)
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        assert workspace.drafts.values["map"] == config
        assert not workspace.drafts.store.messages


def test_nonoverlapping_local_envelope_is_diagnostic_not_invalid_ui_range(inputs, tmp_path):
    manifest, prefs = inputs
    profile = replace(InstrumentProfile(), approved=True, profile_id="test-only",
                      minimum_mirror_voltage_v=20, maximum_mirror_voltage_v=30,
                      home_x_voltage_v=25, home_y_voltage_v=25)
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(asdict(profile)))
    with NativeWorkspace(manifest, preferences_path=prefs, anneal_profile=path) as workspace:
        assert "incompatible" in workspace.drafts.profile_error
        assert workspace.drafts.anneal_base.minimum_mirror_voltage_v < workspace.drafts.anneal_base.maximum_mirror_voltage_v
        with pytest.raises(ValueError, match="profile"):
            workspace.acquire_anneal()


def test_boolean_preference_schema_is_not_integer_version(tmp_path):
    store = WorkspacePreferences("test", "fingerprint", tmp_path / "prefs.json")
    store.path.write_text(json.dumps({"schema_version": True, "configuration_id": "test",
                                     "source_fingerprint": "fingerprint", "workflows": {}}))
    assert store.read() == {}
    assert store.messages
