"""All-hardware composition with injected transports, never physical devices."""

import builtins
import json
import shutil
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from threading import get_ident
from types import SimpleNamespace

import pytest

from labtools.config.anneal_workspace import InstrumentProfile, validate_run_config
from labtools.config.native_candidate import preflight_candidate
from labtools.runtime.hardware_workspace import HardwareWorkspace
from labtools.runtime.session import ResourceBusyError
from labtools.runtime.workspace_settings import alignment_defaults, pack, unpack
from labtools.simulation.operator_session import SimulatedOperatorSession
from labtools.simulation.transport_fakes import (
    TransportTrace,
    map_factories,
    spectrum_factory,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(asdict(InstrumentProfile(profile_id="test-reviewed", approved=True))))
    return tmp_path / "bundle/candidate.json", profile


class FakeLaser:
    def __init__(self, events):
        self.events = events
        self.thread = get_ident()
        self.output = False
        self.current = 0.04
        self.fail_close = False
        self.record("construct")

    def record(self, action):
        assert get_ident() == self.thread
        self.events.append((action, self.thread))

    def identify(self):
        self.record("identify")
        return "Fake ITC4000"

    def get_diode_output(self):
        self.record("read-output")
        return self.output

    def get_current(self):
        self.record("read-current")
        return self.current

    def set_current(self, value):
        self.record("set-current")
        assert value == 0.04
        self.current = value

    def enable_diode(self):
        self.record("on")
        self.output = True

    def disable_diode(self):
        self.record("off")
        self.output = False

    def close(self):
        self.record("close")
        if self.fail_close:
            raise OSError("disconnect failed")
        self.output = False


@pytest.fixture
def rig(bundle, tmp_path):
    manifest, profile = bundle
    events = []
    devices = []
    plan = preflight_candidate(manifest).plan
    trace = TransportTrace()
    fake = SimpleNamespace(trace=trace, map_factories=map_factories(plan.map_config, trace),
                           spectrometer=spectrum_factory(plan.spectrum_request.settings, trace))

    def laser():
        value = FakeLaser(events)
        devices.append(value)
        return value

    anneals = []

    def anneal(config, **kwargs):
        anneals.append(config)
        return "anneal-complete"

    workspace = HardwareWorkspace(manifest, anneal_profile=profile, preferences_path=tmp_path / "prefs.json",
                                  map_factories=fake.map_factories, spectrometer_factory=fake.spectrometer,
                                  laser_factory=laser, anneal_acquisition=anneal,
                                  auxiliary_action=lambda action, config, coordinate: (action, coordinate))
    workspace.drafts.values["anneal"] = replace(workspace.drafts.values["anneal"], output_root=tmp_path / "anneal")
    yield workspace, events, devices, fake, anneals
    if workspace.laser.connected:
        devices[-1].fail_close = False
        workspace.laser.submit("disconnect").result(5)
    workspace.close()


def test_all_hardware_headless_is_lazy_and_does_not_import_drivers(bundle, tmp_path, monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("labtools.devices", "horiba_sdk", "PyQt6", "serial", "pyvisa", "u6")):
            raise AssertionError("Unexpected native import: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with HardwareWorkspace(bundle[0], anneal_profile=bundle[1], preferences_path=tmp_path / "p.json") as workspace:
        report = workspace.describe()
        assert report["workspace_kind"] == "all-hardware"
        assert report["anneal_ready"]
        assert workspace._operator_spectrum.worker.status().state == "unopened"
        assert not workspace.laser.connected
        assert workspace.laser.output is None


def test_laser_connect_is_read_only_commands_are_worker_affine_and_limits_enforced(rig):
    workspace, events, _, _, _ = rig
    laser = workspace.laser
    laser.submit("connect").result(5)
    assert laser.connected and laser.output is False
    assert not any(action in {"on", "set-current", "off"} for action, _ in events)
    assert {thread for _, thread in events} != {get_ident()}
    for value in (0.08, 0.1, -1, float("nan"), True):
        with pytest.raises(ValueError):
            laser.submit("on", value)
    laser.submit("on", 0.04).result(5)
    assert laser.output is True
    lease = workspace._ownership.reserve("Spectrum")
    try:
        with pytest.raises(ResourceBusyError):
            laser.submit("apply", 0.04).result(5)
        assert laser.output is True and laser.error is None
        laser.submit("off").result(5)
        assert laser.output is False
    finally:
        lease.release()
    laser.submit("disconnect").result(5)
    assert not laser.connected
    assert len({thread for _, thread in events}) == 1
    assert all(state.owner is None for state in workspace._ownership.status().resources)


def test_laser_disconnect_failure_retains_handle_and_lease(rig):
    workspace, _, devices, _, _ = rig
    workspace.laser.submit("connect").result(5)
    devices[-1].fail_close = True
    with pytest.raises(OSError):
        workspace.laser.submit("disconnect").result(5)
    assert workspace.laser.connected and workspace.laser.output is None
    with pytest.raises(ResourceBusyError):
        workspace._ownership.reserve("Laser")
    with pytest.raises(RuntimeError):
        workspace.close()
    devices[-1].fail_close = False
    workspace.laser.submit("disconnect").result(5)


def test_real_map_connection_and_acquisition_use_existing_reservation(rig, tmp_path):
    workspace, _, _, fake, _ = rig
    with pytest.raises(PermissionError):
        workspace.test_map_connections()
    lease = workspace._ownership.reserve("Intensity map")
    try:
        workspace.test_map_connections()
        workspace._map_transport._factories = map_factories(workspace.plan.map_config, fake.trace)
        config = replace(workspace.workflows.map_config(), x_points=2, y_points=2,
                         integration_time_s=0.001, settle_time_s=0.0, save_results=False, output_root=tmp_path)
        result = workspace.acquire_map(config)
        assert result is not None
        with pytest.raises(ResourceBusyError):
            workspace._ownership.reserve("Annealing")
        assert "released" in workspace._device_status["IDQ counter"]
        assert fake.trace.events()
    finally:
        lease.release()


def test_anneal_uses_reviewed_profile_intersection_and_ownership(rig):
    workspace, _, _, _, anneals = rig
    with pytest.raises(PermissionError):
        workspace.acquire_anneal()
    lease = workspace._ownership.reserve("Annealing")
    try:
        config = workspace.anneal_config()
        validate_run_config(config, workspace.effective_anneal_profile())
        assert workspace.acquire_anneal() == "anneal-complete"
        assert anneals[0].instrument_profile_id == "test-reviewed"
        assert workspace.auxiliary("stage-test") == ("stage-test", None)
        with pytest.raises(ValueError):
            workspace.auxiliary("stage-move", 1e9)
        with pytest.raises(ResourceBusyError):
            workspace._ownership.reserve("Spectrum")
    finally:
        lease.release()


def test_missing_anneal_profile_does_not_fall_back_to_defaults(bundle, tmp_path):
    with HardwareWorkspace(bundle[0], preferences_path=tmp_path / "p.json") as workspace:
        assert not workspace.describe()["anneal_ready"]
        with pytest.raises(ValueError, match="profile"):
            workspace.anneal_config()


def test_settings_roundtrip_rejects_identity_backend_and_hardware_fields(bundle, tmp_path):
    with SimulatedOperatorSession(bundle[0], preferences_path=tmp_path / "p.json") as workspace:
        data = pack(workspace, workspace.drafts.values, {}, alignment_defaults(workspace))
        result = unpack(workspace, data)
        assert result["alignment"].configuration_id == workspace.plan.configuration_id
        for key, value in (("configuration_id", "wrong"), ("backend", "real"), ("source_fingerprint", "wrong")):
            invalid = deepcopy(data)
            invalid[key] = value
            with pytest.raises(ValueError):
                unpack(workspace, invalid)
        invalid = deepcopy(data)
        invalid["workflows"]["map"]["safe_voltage_max_v"] = 100
        with pytest.raises(ValueError):
            unpack(workspace, invalid)
        invalid = deepcopy(data)
        invalid["workflows"]["alignment"]["exposure_s"] = 0.001
        with pytest.raises(ValueError):
            unpack(workspace, invalid)


def test_cli_modes_are_explicit_and_mutually_exclusive(bundle, capsys):
    from labtools.cli import main

    main(["workspace", "launch", str(bundle[0]), "--hardware", "--anneal-profile", str(bundle[1]), "--headless"])
    assert json.loads(capsys.readouterr().out)["workspace_kind"] == "all-hardware"
    for other in ("--simulate", "--hardware-spectrum"):
        with pytest.raises(SystemExit) as caught:
            main(["workspace", "launch", str(bundle[0]), "--hardware", other, "--headless"])
        assert caught.value.code == 2


def test_laser_startup_cleanup_failure_preserves_retryable_connection(bundle, tmp_path):
    events = []
    devices = []

    class BrokenIdentity(FakeLaser):
        def identify(self):
            raise OSError("identity failed")

    def factory():
        device = BrokenIdentity(events)
        device.fail_close = True
        devices.append(device)
        return device

    workspace = HardwareWorkspace(bundle[0], anneal_profile=bundle[1], preferences_path=tmp_path / "p.json", laser_factory=factory)
    try:
        with pytest.raises(OSError, match="identity failed"):
            workspace.laser.submit("connect").result(5)
        assert workspace.laser.connected
        with pytest.raises(ResourceBusyError):
            workspace._ownership.reserve("Laser")
        devices[0].fail_close = False
        workspace.laser.submit("disconnect").result(5)
        assert not workspace.laser.connected
    finally:
        workspace.close()


def test_failed_anneal_faults_shared_hardware_but_laser_off_still_works(rig):
    workspace, _, _, _, _ = rig
    workspace.laser.submit("connect").result(5)

    def fail(config, **kwargs):
        raise OSError("shutter cleanup failed")

    workspace._anneal_acquisition = fail
    lease = workspace._ownership.reserve("Annealing")
    try:
        with pytest.raises(OSError):
            workspace.acquire_anneal()
    finally:
        lease.release()
    assert workspace.describe()["hardware_fault"]
    with pytest.raises(RuntimeError, match="teardown"):
        workspace.hardware_ready()
    lease = workspace._ownership.reserve("Spectrum")
    try:
        with pytest.raises(RuntimeError, match="teardown"):
            workspace._operator_spectrum.validate_range(workspace.workflows.spectrum_settings())
    finally:
        lease.release()
    workspace.laser.submit("off").result(5)
    assert workspace.laser.output is False
    workspace.laser.submit("disconnect").result(5)


def test_real_anneal_pipeline_accepts_explicit_profile_without_global_profile_override(bundle, tmp_path, monkeypatch):
    from labtools.acquisition import laser_anneal as acquisition

    events = []

    class Shutter:
        def __init__(self, **kwargs):
            events.append("shutter-connect")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("shutter-release")

        def set_mode(self, mode):
            events.append("shutter-mode")

        def set_enabled(self, value):
            events.append("shutter-open" if value else "shutter-close")

    class Stage:
        def __init__(self, **kwargs):
            events.append("stage-connect")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("stage-release")

        def move_to(self, value):
            events.append("stage-move")

    class Jack:
        def __enter__(self):
            events.append("jack-connect")
            return self

        def __exit__(self, *args):
            events.append("jack-release")

    class Mirror:
        def __init__(self, *args, **kwargs):
            events.append("mirror-construct")

        def move(self, x, y):
            events.append("mirror-move")

    monkeypatch.setattr(acquisition, "SC10", Shutter)
    monkeypatch.setattr(acquisition, "KinesisRotationStage", Stage)
    monkeypatch.setattr(acquisition, "LabJackU6", Jack)
    monkeypatch.setattr(acquisition, "ScanningMirror", Mirror)
    with HardwareWorkspace(bundle[0], anneal_profile=bundle[1], preferences_path=tmp_path / "p.json") as workspace:
        config = replace(workspace.drafts.values["anneal"], x_points=1, y_points=1, passes=1,
                         point_dwell_s=0.0, mirror_settle_s=0.0, output_root=tmp_path / "anneal", save_run_log=False)
        lease = workspace._ownership.reserve("Annealing")
        try:
            result = workspace.acquire_anneal(config)
            assert result.completed and not result.stopped
            assert result.completed_points == 1
            assert events.index("shutter-close") < events.index("stage-connect")
            assert events.count("shutter-open") == 1
            assert events.count("stage-move") == 2
            assert events[-1] == "shutter-release"
        finally:
            lease.release()
