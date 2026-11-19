"""Read-only native input binding; no native imports or execution permission."""

import asyncio
import builtins
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from labtools.config.anneal_workspace import InstrumentProfile
from labtools.config.intensity_map import IntensityMapConfig
from labtools.config.native_candidate import REFERENCE_FIELDS, preflight_candidate
from labtools.config.spectrum import SpectrumSettings
from labtools.measurements.intensity_map import IntensityMapRequest
from labtools.measurements.recipes import MeasurementRecipe, recipe_to_data
from labtools.measurements.spectrum import SpectrumRequest
from labtools.runtime.map_devices import MapTransportFactories
from labtools.runtime.native_candidate import (
    DisabledNativeCandidate,
    NativeExecutionDisabled,
)
from labtools.simulation.ownership import WorkspaceOwnership

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_hardware(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "u6", "serial", "pyvisa", "PyQt6")):
            raise AssertionError("Native/GUI import forbidden in preflight: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.fixture
def manifest(tmp_path):
    # Explicit test fixtures, never installed as approved physical configuration.
    profile = InstrumentProfile(profile_id="fixture-only", approved=True)
    mapping = IntensityMapConfig(-1, 1, 2, -1, 1, 2, backend="real", time_controller_address="fixture-counter",
                                safe_voltage_min_v=-1, safe_voltage_max_v=1, output_root=tmp_path / "outputs")
    spectrum = SpectrumSettings(configuration_id="fixture-candidate", backend="real", preset="syncerity",
                                exposure_s=.065, gain=0, speed=0, slit_width_mm=.1, start_nm=500, end_nm=600)
    (tmp_path / "profile.json").write_text(json.dumps(asdict(profile)), encoding="utf-8")
    (tmp_path / "map.json").write_text(json.dumps(recipe_to_data(MeasurementRecipe(
        "intensity_map", IntensityMapRequest(mapping)))), encoding="utf-8")
    (tmp_path / "spectrum.json").write_text(json.dumps(recipe_to_data(MeasurementRecipe(
        "spectrum", SpectrumRequest(spectrum)))), encoding="utf-8")
    (tmp_path / "review.txt").write_text("TEST ONLY: fixture reference, not physical approval", encoding="utf-8")
    data = {"schema_version": 1, "configuration_id": "fixture-candidate",
            "resources": {"labjack": "fixture-jack", "counter": "fixture-counter",
                          "spectrometer": "fixture-spec", "optical_path": "fixture-path"},
            **dict.fromkeys(REFERENCE_FIELDS, "review.txt")}
    data.update(instrument_profile="profile.json", map_recipe="map.json", spectrum_recipe="spectrum.json")
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def mutate(path, action):
    data = json.loads(path.read_text())
    action(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_template_lists_exact_missing_fields_without_hardware():
    report = preflight_candidate(ROOT / "examples/workspace/native-candidate.template.json")
    fields = {error["field"] for error in report.errors}
    assert fields == {"configuration_id", "resources.labjack", "resources.counter",
                      "resources.spectrometer", "resources.optical_path", *REFERENCE_FIELDS}
    assert not report.to_data()["execution_enabled"]
    assert not report.to_data()["hardware_opened"]


def test_complete_inputs_bind_resource_specific_plan_but_never_enable(manifest):
    report = preflight_candidate(manifest)
    assert not report.errors
    plan = report.plan
    assert plan.map_config.time_controller_address == "fixture-counter"
    assert plan.spectrum_request.settings.configuration_id == plan.configuration_id
    assert set(plan.reservation_config.map_resources) == {"fixture-jack", "fixture-counter", "fixture-path"}
    assert set(plan.reservation_config.spectrum_resources) == {"fixture-spec", "fixture-path"}
    assert not report.to_data()["execution_enabled"]
    assert len(plan.sources) == 9
    plan.verify_sources()


@pytest.mark.parametrize("field", REFERENCE_FIELDS)
def test_missing_reference_is_reported(manifest, field):
    mutate(manifest, lambda data: data.update({field: "missing-file"}))
    report = preflight_candidate(manifest)
    assert field in {error["field"] for error in report.errors}
    assert report.plan is None


@pytest.mark.parametrize("filename,change,expected", [
    ("profile.json", lambda data: data.update(approved=False), "instrument_profile"),
    ("profile.json", lambda data: data.update(home_x_voltage_v=.1), "instrument_profile.home"),
    ("map.json", lambda data: data["recipe"]["config"].update(mirror_dio_pin=4), "map_recipe.config.mirror_dio_pin"),
    ("map.json", lambda data: data["recipe"]["config"].update(spad_gate_pin=2), "map_recipe.config.spad_gate_pin"),
    ("map.json", lambda data: data["recipe"]["config"].update(safe_voltage_min_v=-11), "map_recipe.config.safe_voltage_limits"),
    ("map.json", lambda data: data["recipe"]["config"].update(backend="simulation"), "map_recipe"),
    ("spectrum.json", lambda data: data["recipe"]["settings"].update(configuration_id="wrong"), "spectrum_recipe"),
    ("spectrum.json", lambda data: data["recipe"]["settings"].update(backend="simulation"), "spectrum_recipe"),
])
def test_inconsistent_inputs_are_refused(manifest, filename, change, expected):
    mutate(manifest.parent / filename, change)
    report = preflight_candidate(manifest)
    assert expected in {error["field"] for error in report.errors}
    assert report.plan is None


def test_unknown_and_duplicate_keys_refused(manifest):
    mutate(manifest, lambda data: data.update(execute=True))
    assert preflight_candidate(manifest).errors[0]["field"] == "manifest"
    manifest.write_text('{"schema_version":1,"schema_version":1}')
    assert "Duplicate" in preflight_candidate(manifest).errors[0]["message"]


def test_changed_source_cannot_be_bound(manifest):
    plan = preflight_candidate(manifest).plan
    (manifest.parent / "review.txt").write_text("changed")
    with pytest.raises(ValueError, match="source changed"):
        plan.verify_sources()


def test_disabled_composition_refuses_map_spectrum_and_dark_before_factories(manifest):
    plan = preflight_candidate(manifest).plan
    ownership = WorkspaceOwnership(plan.reservation_config)

    def forbidden(*args, **kwargs):
        pytest.fail("No transport may be constructed in disabled candidate")

    try:
        candidate = DisabledNativeCandidate(
            plan=plan, ownership=ownership,
            map_factories=MapTransportFactories(forbidden, forbidden, forbidden, forbidden),
            spectrometer_factory=forbidden,
        )
        assert not candidate.describe()["execution_enabled"]
        with ownership.reserve("Intensity map"), pytest.raises(NativeExecutionDisabled):
            candidate.acquire_map(plan.map_config)
        with ownership.reserve("Spectrum"):
            with pytest.raises(NativeExecutionDisabled):
                asyncio.run(candidate.spectrum.acquire(plan.spectrum_request.settings))
            with pytest.raises(NativeExecutionDisabled):
                asyncio.run(candidate.spectrum.capture_dark(plan.spectrum_request.settings))
        assert not ownership.session.reservations()
    finally:
        ownership.close()


def test_cli_is_read_only_and_has_no_enable_flag(manifest, capsys):
    from labtools.cli import main

    main(["workspace", "preflight", str(manifest)])
    report = json.loads(capsys.readouterr().out)
    assert report["inputs_complete"] and not report["execution_enabled"]
    with pytest.raises(SystemExit) as caught:
        main(["workspace", "preflight", str(manifest), "--execute"])
    assert caught.value.code == 2


def test_missing_manifest_returns_structured_error(tmp_path):
    report = preflight_candidate(tmp_path / "missing.json")
    assert report.errors[0]["field"] == "manifest"


def test_pre_taken_dark_rejected_without_opening_archive(manifest):
    mutate(manifest.parent / "spectrum.json", lambda data: data["recipe"].update(
        dark_mode="pre_taken", dark_record_path="must-not-open.npz"))
    report = preflight_candidate(manifest)
    error = next(error for error in report.errors if error["field"] == "spectrum_recipe")
    assert "base recipe" in error["message"]


def test_cli_missing_inputs_are_machine_readable_and_stay_disabled(capsys):
    from labtools.cli import main

    with pytest.raises(SystemExit) as caught:
        main(["workspace", "preflight", str(ROOT / "examples/workspace/native-candidate.template.json")])
    assert caught.value.code == 2
    data = json.loads(capsys.readouterr().out)
    assert not data["inputs_complete"] and not data["execution_enabled"]
    assert len(data["input_errors"]) == 13


def test_ownership_layout_mismatch_refuses_binding(manifest):
    plan = preflight_candidate(manifest).plan
    ownership = WorkspaceOwnership()

    def forbidden(*args, **kwargs):
        pytest.fail("Factory must not be called")

    try:
        with pytest.raises(ValueError, match="Ownership resources"):
            DisabledNativeCandidate(
                plan=plan, ownership=ownership,
                map_factories=MapTransportFactories(forbidden, forbidden, forbidden, forbidden),
                spectrometer_factory=forbidden,
            )
    finally:
        ownership.close()
