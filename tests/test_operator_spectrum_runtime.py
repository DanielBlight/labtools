"""Unified ownership and real-adapter contract using fake devices, never hardware."""

import asyncio
import builtins
import json
import shutil
import time
from dataclasses import replace
from pathlib import Path
from threading import Event, get_ident
from types import SimpleNamespace

import numpy as np
import pytest

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.runtime.hardware_spectrum_workspace import HardwareSpectrumWorkspace
from labtools.runtime.native_candidate import NativeExecutionDisabled
from labtools.runtime.operator_spectrum import ensure_operator_spectrum
from labtools.runtime.session import ResourceBusyError
from labtools.runtime.spectrum_worker import (
    SpectrumWorkerBusyError,
    SpectrumWorkerFaultedError,
)
from labtools.simulation.operator_session import SimulatedOperatorSession

ROOT = Path(__file__).resolve().parents[1]


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, "Worker lifecycle timed out"
        time.sleep(0.002)


@pytest.fixture
def manifest(tmp_path):
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    return tmp_path / "bundle/candidate.json"


class FakeSpectrometer:
    def __init__(self, *, preset, rig):
        self.rig = rig
        self.thread = get_ident()
        self.loop = asyncio.get_running_loop()
        self.ccd = SimpleNamespace(range_mode_center_wavelengths=self.centres)
        self.mono = SimpleNamespace(id=lambda: 1)
        self.record("construct")

    def record(self, name):
        assert get_ident() == self.thread
        assert asyncio.get_running_loop() is self.loop
        self.rig.events.append((name, self.thread, id(self.loop)))

    async def connect(self):
        self.record("connect")

    async def configure(self, **kwargs):
        self.record("configure")

    async def set_wavelength(self, value):
        self.record("move")
        return value

    async def prepare_wavelength_axis(self):
        return 690.0

    async def centres(self, *args):
        return [690.0]

    async def get_spectrum(self, **kwargs):
        self.record("capture")
        self.rig.frames += 1
        await asyncio.sleep(0.002)
        if self.rig.fail_capture:
            raise OSError("capture failed")
        return np.array([685.0, 690.0, 695.0]), np.array([1.0, 4.0, 1.0])

    async def get_dark_spectrum(self, **kwargs):
        self.record("dark")
        return np.array([685.0, 690.0, 695.0]), np.array([0.1, 0.1, 0.1])

    async def disconnect(self):
        self.record("disconnect-start")
        self.rig.cleaning.set()
        while not self.rig.allow_cleanup.is_set():
            await asyncio.sleep(0.001)
        self.record("disconnect")
        if self.rig.fail_cleanup:
            raise OSError("disconnect failed")


@pytest.fixture
def rig():
    rig = SimpleNamespace(events=[], frames=0, cleaning=Event(), allow_cleanup=Event(), fail_capture=False, fail_cleanup=False)
    rig.allow_cleanup.set()
    return rig


def make_workspace(manifest, tmp_path, rig):
    return HardwareSpectrumWorkspace(
        manifest, preferences_path=tmp_path / "prefs.json",
        spectrometer_factory=lambda **kwargs: FakeSpectrometer(rig=rig, **kwargs),
    )


def alignment(workspace):
    return AlignmentSettings(workspace.plan.configuration_id, centre_nm=690.0, exposure_s=0.1)


def test_headless_hardware_launch_is_lazy_and_other_workflows_stay_gated(manifest, tmp_path, monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("labtools.devices", "horiba_sdk", "PyQt6", "serial", "pyvisa", "u6")):
            raise AssertionError("Unexpected native/GUI import: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with HardwareSpectrumWorkspace(manifest, preferences_path=tmp_path / "prefs.json") as workspace:
        report = workspace.describe()
        assert report["enabled_workflows"] == ["Spectrum", "Alignment"]
        assert not report["hardware_opened"]
        assert workspace._operator_spectrum.worker.status().state == "unopened"
        with pytest.raises(NativeExecutionDisabled):
            workspace.acquire_map()
        with pytest.raises(NativeExecutionDisabled):
            workspace.acquire_anneal()


def test_stream_lease_blocks_spectrum_map_anneal_and_survives_cleanup(manifest, tmp_path, rig):
    workspace = make_workspace(manifest, tmp_path, rig)
    runtime = workspace._operator_spectrum
    lease = workspace._ownership.reserve("Spectrum")
    rig.allow_cleanup.clear()
    job = runtime.worker.start_alignment(alignment(workspace), owner="Spectrum")
    try:
        wait_for(lambda: rig.frames >= 5)
        for owner in ("Spectrum", "Intensity map", "Annealing"):
            with pytest.raises(ResourceBusyError):
                workspace._ownership.reserve(owner)
        with pytest.raises(SpectrumWorkerBusyError):
            runtime.worker.acquire_alignment(alignment(workspace))
        job.cancel()
        wait_for(rig.cleaning.is_set)
        assert not job.done() and runtime.worker.status().state == "busy"
        with pytest.raises(SpectrumWorkerBusyError):
            workspace.close()
        rig.allow_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            job.result(5)
        assert runtime.worker.status().state == "available"
        assert len({event[1:] for event in rig.events}) == 1
        assert [event[0] for event in rig.events].count("connect") == 1
        assert [event[0] for event in rig.events].count("disconnect") == 1
        second = runtime.worker.start_alignment(alignment(workspace), owner="Spectrum")
        wait_for(lambda: [e[0] for e in rig.events].count("connect") == 2)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            second.result(5)
    finally:
        rig.allow_cleanup.set()
        job.cancel()
        wait_for(lambda: runtime.worker.status().state != "busy")
        lease.release()
        workspace.close()


def test_range_facade_uses_same_worker_thread_and_loop_as_alignment(manifest, tmp_path, rig):
    workspace = make_workspace(manifest, tmp_path, rig)
    runtime = workspace._operator_spectrum
    lease = workspace._ownership.reserve("Spectrum")
    try:
        asyncio.run(workspace.spectrum_service.test_connection(workspace.workflows.spectrum_settings()))
        job = runtime.worker.start_alignment(alignment(workspace), owner="Spectrum")
        wait_for(lambda: rig.frames >= 2)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            job.result(5)
        assert len({event[1:] for event in rig.events}) == 1
        assert [e[0] for e in rig.events].count("connect") == 2
        assert workspace.describe()["hardware_opened"] is None
    finally:
        lease.release()
        workspace.close()


@pytest.mark.parametrize("failure", ["capture", "disconnect"])
def test_fault_is_shared_by_range_and_alignment(manifest, tmp_path, rig, failure):
    workspace = make_workspace(manifest, tmp_path, rig)
    runtime = workspace._operator_spectrum
    lease = workspace._ownership.reserve("Spectrum")
    rig.fail_capture = failure == "capture"
    rig.fail_cleanup = failure == "disconnect"
    job = runtime.worker.start_alignment(alignment(workspace), owner="Spectrum")
    try:
        wait_for(lambda: rig.frames >= 1)
        if failure == "disconnect":
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                job.result(5)
        else:
            with pytest.raises(OSError):
                job.result(5)
        assert runtime.worker.status().state == "faulted"
        with pytest.raises(SpectrumWorkerFaultedError):
            asyncio.run(workspace.spectrum_service.test_connection(workspace.workflows.spectrum_settings()))
    finally:
        lease.release()
        workspace.close()


def test_source_and_backend_validation_precede_device_construction(manifest, tmp_path, rig):
    workspace = make_workspace(manifest, tmp_path, rig)
    runtime = workspace._operator_spectrum
    with pytest.raises(PermissionError):
        runtime.validate_alignment(alignment(workspace))
    lease = workspace._ownership.reserve("Spectrum")
    try:
        with pytest.raises(ValueError):
            runtime.validate_alignment(replace(alignment(workspace), backend="simulation"))
        with pytest.raises(ValueError):
            runtime.validate_alignment(replace(alignment(workspace), exposure_s=0.001))
        manifest.write_text("{}")
        with pytest.raises(ValueError, match="source changed"):
            runtime.validate_alignment(alignment(workspace))
        assert not rig.events
    finally:
        lease.release()
        workspace.close()


def test_simulated_stream_uses_shared_worker_without_native_imports(manifest, tmp_path, monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("labtools.devices", "horiba_sdk")):
            raise AssertionError("Native import in simulation")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with SimulatedOperatorSession(manifest, preferences_path=tmp_path / "sim.json") as workspace:
        runtime = ensure_operator_spectrum(workspace)
        assert ensure_operator_spectrum(workspace) is runtime
        lease = workspace._ownership.reserve("Spectrum")
        job = runtime.worker.start_alignment(replace(alignment(workspace), backend="simulation"), owner="Spectrum")
        try:
            wait_for(lambda: job.take_latest() is not None)
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                job.result(5)
            assert runtime.worker.status().state == "available"
        finally:
            job.cancel()
            wait_for(job.done)
            lease.release()
    assert runtime.worker.status().state == "closed"


def test_cli_hardware_mode_is_explicit_and_excludes_simulation(manifest, capsys):
    from labtools.cli import main

    main(["workspace", "launch", str(manifest), "--hardware-spectrum", "--headless"])
    report = json.loads(capsys.readouterr().out)
    assert report["workspace_kind"] == "hardware-spectrum"
    assert not report["hardware_opened"]
    with pytest.raises(SystemExit) as caught:
        main(["workspace", "launch", str(manifest), "--hardware-spectrum", "--simulate", "--headless"])
    assert caught.value.code == 2


def test_cancelled_before_range_submission_never_opens_device(manifest, tmp_path, rig):
    with make_workspace(manifest, tmp_path, rig) as workspace:
        lease = workspace._ownership.reserve("Spectrum")
        try:
            with pytest.raises(asyncio.CancelledError):
                asyncio.run(workspace.spectrum_service.test_connection(
                    workspace.workflows.spectrum_settings(), cancel_requested=lambda: True,
                ))
            assert not rig.events
            assert workspace._operator_spectrum.worker.status().state == "unopened"
        finally:
            lease.release()


def test_range_acquire_and_reusable_dark_share_the_worker(manifest, tmp_path, rig):
    def stitch(captures, start, end):
        return np.array(captures[0][0]), np.array(captures[0][1][0])

    with HardwareSpectrumWorkspace(
        manifest, preferences_path=tmp_path / "prefs.json",
        spectrometer_factory=lambda **kwargs: FakeSpectrometer(rig=rig, **kwargs), stitcher=stitch,
    ) as workspace:
        lease = workspace._ownership.reserve("Spectrum")
        try:
            settings = workspace.workflows.spectrum_settings()
            dark = asyncio.run(workspace.spectrum_service.capture_dark(settings))
            result = asyncio.run(workspace.spectrum_service.acquire(settings, dark_mode="pre_taken", dark=dark))
            assert result.dark_mode == "pre_taken"
            np.testing.assert_allclose(result.intensity, [0.9, 3.9, 0.9])
            assert len({event[1:] for event in rig.events}) == 1
        finally:
            lease.release()


def test_source_preset_mismatch_refuses_before_native_construction(manifest, tmp_path, monkeypatch):
    import sys
    from copy import deepcopy
    from enum import Enum
    from types import ModuleType

    with HardwareSpectrumWorkspace(manifest, preferences_path=tmp_path / "prefs.json") as workspace:
        calls = []
        presets = deepcopy(workspace.plan.hardware_settings["detectors"])
        for options in presets.values():
            for field in ("grating", "mirror_position"):
                options[field] = Enum("Choice", {options[field]: 1})[options[field]]

        class FakeWrapper:
            PRESETS = presets

            def __init__(self, *, preset):
                calls.append(preset)

        module = ModuleType("labtools.devices.horiba_spectrometer")
        module.HoribaSpectrometer = FakeWrapper
        monkeypatch.setitem(sys.modules, module.__name__, module)
        workspace._source_spectrometer(preset="syncerity")
        assert calls == ["syncerity"]
        FakeWrapper.PRESETS["syncerity"]["expected_serial_number"] = "wrong serial"
        with pytest.raises(ValueError, match="expected_serial_number"):
            workspace._source_spectrometer(preset="syncerity")
        assert calls == ["syncerity"]
