"""Migrated lab settings, disabled binding and authorized default limit change."""

import ast
import asyncio
import builtins
import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from labtools.config.anneal_workspace import (
    AnnealRecipe,
    InstrumentProfile,
    load_profile,
    validate_recipe,
)
from labtools.config.native_candidate import preflight_candidate
from labtools.runtime.map_devices import MapTransportFactories
from labtools.runtime.native_candidate import (
    DisabledNativeCandidate,
    NativeExecutionDisabled,
)
from labtools.simulation.ownership import WorkspaceOwnership

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "examples/workspace/working-lab"


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "u6", "serial", "pyvisa", "PyQt6")):
            raise AssertionError("Native/GUI import forbidden: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.fixture
def candidate(tmp_path):
    shutil.copytree(BUNDLE, tmp_path / "bundle")
    return tmp_path / "bundle/candidate.json"


def edit(candidate, filename, action):
    path = candidate.parent / filename
    data = json.loads(path.read_text())
    action(data)
    path.write_text(json.dumps(data))


def test_migrated_preflight_is_complete_not_enabled(candidate):
    report = preflight_candidate(candidate)
    assert not report.errors
    data = report.to_data()
    assert data["inputs_complete"] and not data["execution_enabled"]
    assert not data["hardware_opened"] and not data["environment_probed"]
    assert len(data["runtime_inputs"]) == 6
    plan = report.plan
    assert len(plan.sources) == 5
    plan.verify_sources()
    assert plan.map_config.safe_voltage_min_v == -10
    assert plan.map_config.safe_voltage_max_v == 10
    assert plan.map_config.time_controller_address == "169.254.99.159"
    assert (plan.map_config.mirror_dio_pin, plan.map_config.spad_gate_pin) == (2, 0)
    assert plan.map_config.x_points == plan.map_config.y_points == 40
    assert plan.spectrum_request.settings.gain == 2
    assert plan.spectrum_request.settings.exposure_s == .5
    assert plan.hardware_settings["detectors"]["syncerity"]["expected_serial_number"] == "Camera SN: 926"
    assert set(plan.reservation_config.map_resources) & set(plan.reservation_config.spectrum_resources) == {"working-lab-optical-path"}
    assert "instrument_profile" not in json.loads(candidate.read_text())


@pytest.mark.parametrize("filename,action", [
    ("candidate.json", lambda d: d.update(execute=True)),
    ("candidate.json", lambda d: d.update(source_record="absent.json")),
    ("candidate.json", lambda d: d["resources"].update(counter=d["resources"]["labjack"])),
    ("profile.json", lambda d: d.update(approved=True)),
    ("profile.json", lambda d: d.update(gate_active_high=False)),
    ("profile.json", lambda d: d.update(mirror_dio_pin=True)),
    ("profile.json", lambda d: d.update(spad_gate_pin=3)),
    ("profile.json", lambda d: d.update(home_x_voltage_v=1)),
    ("profile.json", lambda d: d.update(minimum_mirror_voltage_v=float("nan"))),
    ("profile.json", lambda d: d.update(counter_port=True)),
    ("profile.json", lambda d: d.update(labjack_selection="invented-serial")),
    ("profile.json", lambda d: d["detectors"]["syncerity"]["roi"].update(x_size=2048)),
    ("profile.json", lambda d: d["detectors"]["syncerity"].update(gains=["bad"])),
    ("map.json", lambda d: d["recipe"]["config"].update(time_controller_address="wrong")),
    ("map.json", lambda d: d["recipe"]["config"].update(safe_voltage_min_v=-11)),
    ("map.json", lambda d: d["recipe"]["config"].update(backend="simulation")),
    ("spectrum.json", lambda d: d["recipe"]["settings"].update(configuration_id="wrong")),
    ("spectrum.json", lambda d: d["recipe"]["settings"].update(exposure_s=.02)),
    ("spectrum.json", lambda d: d["recipe"]["settings"].update(gain=99)),
    ("spectrum.json", lambda d: d["recipe"].update(dark_mode="pre_taken", dark_record_path="never-open.npz")),
    ("source-record.json", lambda d: d.update(snapshot_sha256="invalid")),
])
def test_inconsistent_or_unsupported_input_refused(candidate, filename, action):
    edit(candidate, filename, action)
    report = preflight_candidate(candidate)
    assert report.errors and report.plan is None
    assert not report.to_data()["execution_enabled"]


def test_source_change_rejected_before_binding(candidate):
    plan = preflight_candidate(candidate).plan
    (candidate.parent / "source-record.json").write_text("{}")
    with pytest.raises(ValueError, match="source changed"):
        plan.verify_sources()


def test_source_plan_refuses_every_native_operation_and_releases_leases(candidate):
    plan = preflight_candidate(candidate).plan
    ownership = WorkspaceOwnership(plan.reservation_config)

    def forbidden(*args, **kwargs):
        pytest.fail("Disabled candidate constructed a device")

    try:
        service = DisabledNativeCandidate(
            plan=plan, ownership=ownership,
            map_factories=MapTransportFactories(forbidden, forbidden, forbidden, forbidden),
            spectrometer_factory=forbidden,
        )
        for _ in range(2):
            with ownership.reserve("Intensity map"), pytest.raises(NativeExecutionDisabled):
                service.acquire_map(plan.map_config)
            with ownership.reserve("Spectrum"):
                with pytest.raises(NativeExecutionDisabled):
                    asyncio.run(service.spectrum.acquire(plan.spectrum_request.settings))
                with pytest.raises(NativeExecutionDisabled):
                    asyncio.run(service.spectrum.capture_dark(plan.spectrum_request.settings))
            assert not ownership.session.reservations()
    finally:
        ownership.close()


def test_cli_reports_runtime_inputs_without_probe(candidate, capsys):
    from labtools.cli import main

    main(["workspace", "preflight", str(candidate)])
    data = json.loads(capsys.readouterr().out)
    assert data["inputs_complete"] and not data["execution_enabled"]
    assert data["runtime_inputs"]


def test_anneal_defaults_aligned_but_explicit_local_profile_preserved(tmp_path):
    profile = InstrumentProfile()
    assert (profile.minimum_mirror_voltage_v, profile.maximum_mirror_voltage_v) == (-10, 10)
    approved = replace(profile, approved=True, profile_id="test-only")
    recipe = replace(AnnealRecipe(), x_start_v=-10, x_stop_v=10, output_root=str(tmp_path.resolve()))
    validate_recipe(recipe, approved)
    for voltage in (-10.01, 10.01):
        with pytest.raises(ValueError):
            validate_recipe(replace(recipe, x_stop_v=voltage), approved)
    narrow = replace(approved, minimum_mirror_voltage_v=-5, maximum_mirror_voltage_v=5)
    path = tmp_path / "existing-profile.json"
    path.write_text(json.dumps(asdict(narrow)))
    before = path.read_bytes()
    assert load_profile(path) == narrow
    assert path.read_bytes() == before
    with pytest.raises(ValueError):
        validate_recipe(recipe, narrow)
    # Read the actual acquisition dataclass defaults without importing devices.
    tree = ast.parse((ROOT / "src/labtools/config/anneal_types.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LaserAnnealConfig")
    defaults = {n.target.id: ast.literal_eval(n.value) for n in cls.body
                if isinstance(n, ast.AnnAssign) and n.target.id in
                {"minimum_mirror_voltage_v", "maximum_mirror_voltage_v"}}
    assert defaults == {"minimum_mirror_voltage_v": -10, "maximum_mirror_voltage_v": 10}


def test_migrated_detector_presets_match_development_wrapper_without_sdk_import():
    tree = ast.parse((ROOT / "src/labtools/devices/horiba_spectrometer.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HoribaSpectrometer")
    node = next(n.value for n in cls.body if isinstance(n, ast.AnnAssign) and n.target.id == "PRESETS")

    def literal(n):
        if isinstance(n, ast.Attribute):
            return n.attr
        if isinstance(n, ast.Name):
            return {"CCD_SYNCERITY": 1, "CCD_SYMPHONY": 0}[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "detector_options":
            from labtools.config.horiba_presets import detector_options

            return json.loads(json.dumps(detector_options(ast.literal_eval(n.args[0]))))
        if isinstance(n, ast.Dict):
            result = {}
            for key, val in zip(n.keys, n.values, strict=True):
                if key is None:
                    result.update(literal(val))
                else:
                    result[literal(key)] = literal(val)
            return result
        if isinstance(n, (ast.List, ast.Tuple)):
            return [literal(item) for item in n.elts]
        return ast.literal_eval(n)

    assert literal(node) == json.loads((BUNDLE / "profile.json").read_text())["detectors"]
