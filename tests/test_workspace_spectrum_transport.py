"""Exercise the actual native adapter/range code with fake transports only."""

import asyncio
import builtins
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import get_ident
from types import SimpleNamespace

import numpy as np
import pytest

from labtools.config.spectrum import SpectrumSettings
from labtools.config.workspace import WorkspaceConfig
from labtools.runtime.workspace_spectrum_transport import WorkspaceSpectrumTransport
from labtools.simulation.ownership import WorkspaceOwnership


def settings():
    return SpectrumSettings(configuration_id="transport-test", backend="real", preset="syncerity",
                            exposure_s=.065, gain=0, speed=0, slit_width_mm=.1,
                            start_nm=500, end_nm=600, overlap_pixels=0)


@pytest.fixture
def rig(monkeypatch):
    from labtools.acquisition import range_spectrum

    original_import = builtins.__import__

    def forbid_native(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "pyvisa", "u6", "serial")):
            raise AssertionError("Native import forbidden in transport test: " + name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbid_native)
    # SDK stitching is not under test: one fake centre, identity stitching/filtering.
    def fake_stitch(captures, start, end):
        assert len(captures) == 1
        x = np.asarray(captures[0][0])
        y = np.asarray(captures[0][1][0])
        keep = (x >= min(start, end)) & (x <= max(start, end))
        return x[keep], y[keep]

    monkeypatch.setattr(range_spectrum, "_stitch_and_filter", fake_stitch)
    ownership = WorkspaceOwnership(WorkspaceConfig(configuration_id="transport-test"))
    events = []
    instances = []
    primary = ValueError("fake acquisition failed")
    cleanup = OSError("fake disconnect failed")
    failures = {"connect": False, "configure": False, "acquire": False, "disconnect": False}

    class FakeSpectrometer:
        def __init__(self, *, preset):
            self.thread = get_ident()
            self.loop = asyncio.get_running_loop()
            self.closed = False
            self.preset = preset
            self.ccd = SimpleNamespace(range_mode_center_wavelengths=self.centres)
            self.mono = SimpleNamespace(id=lambda: 1)
            instances.append(self)
            self.record("construct")

        def record(self, action):
            assert get_ident() == self.thread
            assert asyncio.get_running_loop() is self.loop
            assert not self.closed
            events.append((len(instances), action, get_ident(), id(self.loop)))

        async def connect(self):
            self.record("connect")
            if failures["connect"]:
                raise primary

        async def configure(self, **kwargs):
            self.record("configure")
            assert kwargs["exposure_time"] == .065
            if failures["configure"]:
                raise primary

        async def prepare_wavelength_axis(self):
            self.record("prepare")
            return 550.0

        async def centres(self, *args):
            self.record("centres")
            return [550.0]

        async def set_wavelength(self, value):
            self.record("wavelength")
            return value

        async def get_spectrum(self, **kwargs):
            self.record("acquire")
            if failures["acquire"]:
                raise primary
            return np.array([500., 550., 600.]), np.array([12., 22., 12.])

        async def get_dark_spectrum(self, **kwargs):
            self.record("dark")
            return np.array([500., 550., 600.]), np.array([2., 2., 2.])

        async def disconnect(self):
            self.record("disconnect")
            self.closed = True
            if failures["disconnect"]:
                raise cleanup

    boundary = WorkspaceSpectrumTransport(ownership=ownership, spectrometer_factory=FakeSpectrometer)
    try:
        yield ownership, boundary, instances, events, failures, primary, cleanup
    finally:
        ownership.close()


def test_missing_factory_is_rejected(rig):
    ownership, *_ = rig
    with pytest.raises(TypeError):
        WorkspaceSpectrumTransport(ownership=ownership, spectrometer_factory=None)


@pytest.mark.parametrize("change", [{}, {"backend": "simulation"}, {"configuration_id": "other"}])
def test_refusal_precedes_factory_construction(rig, change):
    _, boundary, instances, *_ = rig
    with pytest.raises((PermissionError, ValueError)):
        asyncio.run(boundary.service.acquire(replace(settings(), **change)))
    assert not instances


def test_actual_adapter_repeat_keeps_each_handle_on_its_worker_loop(rig):
    ownership, boundary, instances, events, *_ = rig
    ui_thread = get_ident()
    for _ in range(2):
        with ownership.reserve("Spectrum"):
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(lambda: asyncio.run(boundary.service.acquire(settings()))).result()
            np.testing.assert_array_equal(result.intensity, [12., 22., 12.])
            assert instances[-1].closed
            assert ownership.status().resources[0].owner == "Spectrum"
    assert len(instances) == 2 and instances[0] is not instances[1]
    for instance in instances:
        assert instance.thread != ui_thread
    groups = [[event for event in events if event[0] == number] for number in (1, 2)]
    for group in groups:
        assert group[0][1] == "construct" and group[-1][1] == "disconnect"
        assert len({(event[2], event[3]) for event in group}) == 1
    assert ownership.status().resources[0].owner is None


@pytest.mark.parametrize("phase", ["connect", "configure", "acquire"])
def test_failure_disconnect_preserves_primary_and_lease(rig, phase):
    ownership, boundary, instances, _, failures, primary, cleanup = rig
    failures[phase] = True
    failures["disconnect"] = True
    with ownership.reserve("Spectrum"):
        with pytest.raises(ValueError) as caught:
            asyncio.run(boundary.service.acquire(settings()))
        assert caught.value is primary
        assert primary._horiba_cleanup_failures[-1] is cleanup
        assert instances[-1].closed
        assert ownership.status().resources[0].owner == "Spectrum"


def test_disconnect_only_failure_propagates(rig):
    ownership, boundary, instances, _, failures, _, cleanup = rig
    failures["disconnect"] = True
    with ownership.reserve("Spectrum"), pytest.raises(OSError) as caught:
        asyncio.run(boundary.service.acquire(settings()))
    assert caught.value is cleanup and instances[-1].closed


def test_dark_subtraction_and_cancellation_reuse(rig):
    ownership, boundary, instances, *_ = rig

    async def workflow():
        dark = await boundary.service.capture_dark(settings())
        result = await boundary.service.acquire(settings(), dark_mode="pre_taken", dark=dark)
        np.testing.assert_array_equal(result.intensity, [10., 20., 10.])
        before = len(instances)
        with pytest.raises(asyncio.CancelledError):
            await boundary.service.acquire(settings(), cancel_requested=lambda: True)
        assert len(instances) == before
        await boundary.service.acquire(settings())

    with ownership.reserve("Spectrum"):
        asyncio.run(workflow())
    assert all(instance.closed for instance in instances)


def test_cancellation_inside_adapter_disconnects_before_release(rig):
    ownership, boundary, instances, *_ = rig

    async def workflow():
        async with boundary._backend(settings()):
            raise asyncio.CancelledError

    with ownership.reserve("Spectrum"), pytest.raises(asyncio.CancelledError):
        asyncio.run(workflow())
    assert instances[-1].closed


def test_closed_proxy_and_cross_loop_use_refused(rig):
    ownership, boundary, instances, *_ = rig

    async def workflow():
        async with boundary._backend(settings()) as proxy:
            with (
                ThreadPoolExecutor(max_workers=1) as executor,
                pytest.raises(RuntimeError, match="thread/loop/lifetime"),
            ):
                executor.submit(lambda: asyncio.run(proxy.acquire("none"))).result()
        with pytest.raises(RuntimeError, match="thread/loop/lifetime"):
            await proxy.acquire("none")

    with ownership.reserve("Spectrum"):
        asyncio.run(workflow())
    assert instances[-1].closed


def test_map_reservation_conflict_blocks_transport(rig):
    ownership, boundary, instances, *_ = rig
    with ownership.reserve("Intensity map"), pytest.raises(PermissionError):
        asyncio.run(boundary.service.acquire(settings()))
    assert not instances


def test_cancel_and_disconnect_failure_preserves_cancellation(rig):
    ownership, boundary, instances, _, failures, _, cleanup = rig
    failures["disconnect"] = True
    cancellation = asyncio.CancelledError()

    async def workflow():
        async with boundary._backend(settings()):
            raise cancellation

    with ownership.reserve("Spectrum"):
        with pytest.raises(asyncio.CancelledError) as caught:
            asyncio.run(workflow())
        assert caught.value is cancellation
        assert cancellation._horiba_cleanup_failures[-1] is cleanup
        assert instances[-1].closed
        assert ownership.status().resources[0].owner == "Spectrum"
