"""Whole HORIBA wrapper lifecycle tests with an isolated fake SDK; no hardware."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from enum import Enum
from pathlib import Path
from threading import get_ident
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


class Value(Enum):
    FIRST = 1
    SECOND = 2
    THIRD = 3
    AXIAL = 10
    LATERAL = 11
    SPECTRA_IMAGE = 20
    MILLISECONDS = 30
    FROM_ICL_SETTINGS_INI = 40


class FakeSDK:
    def __init__(self):
        self.events = []
        self.failures = {}
        self.thread_loop = []
        self.configuration = {
            "deviceType": "HORIBA Syncerity",
            "chipWidth": 1024,
            "chipHeight": 256,
            "serialNumber": "Camera SN: 926",
            "gains": [0, 1, 2],
            "speeds": [0, 1, 2, 127],
        }
        owner = self

        class Mono:
            async def open(self):
                owner.record("mono-open")

            async def close(self):
                owner.record("mono-close")

            async def is_busy(self):
                owner.record("mono-busy")
                return False

        class CCD:
            def __init__(self, label):
                self.label = label

            async def open(self):
                owner.record(self.label + "-open")

            async def close(self):
                owner.record(self.label + "-close")

            async def get_acquisition_busy(self):
                owner.record(self.label + "-busy")
                return False

            async def get_configuration(self):
                owner.record(self.label + "-configuration")
                return dict(owner.configuration)

        self.mono = Mono()
        self.other_ccd = CCD("other-ccd")
        self.ccd = CCD("ccd")

        class Manager:
            def __init__(self):
                self.monochromators = [owner.mono]
                self.charge_coupled_devices = [owner.other_ccd, owner.ccd]

            async def start(self):
                owner.record("manager-start")

            async def stop(self):
                owner.record("manager-stop")

        self.manager = Manager()

    def record(self, name):
        self.events.append(name)
        self.thread_loop.append((get_ident(), id(asyncio.get_running_loop())))
        failure = self.failures.get(name)
        if failure is not None:
            raise failure

    def manager_factory(self, *, start_icl):
        assert start_icl is True
        self.events.append("manager-create")
        self.thread_loop.append((get_ident(), id(asyncio.get_running_loop())))
        failure = self.failures.get("manager-create")
        if failure is not None:
            raise failure
        return self.manager


@pytest.fixture
def wrapper(monkeypatch):
    sdk = FakeSDK()
    modules = {}

    class Monochromator:
        Grating = Value
        MirrorPosition = Value

    paths = {
        "horiba_sdk": ModuleType("horiba_sdk"),
        "horiba_sdk.core": ModuleType("horiba_sdk.core"),
        "horiba_sdk.core.acquisition_format": ModuleType(
            "horiba_sdk.core.acquisition_format"
        ),
        "horiba_sdk.core.timer_resolution": ModuleType(
            "horiba_sdk.core.timer_resolution"
        ),
        "horiba_sdk.core.x_axis_conversion_type": ModuleType(
            "horiba_sdk.core.x_axis_conversion_type"
        ),
        "horiba_sdk.devices": ModuleType("horiba_sdk.devices"),
        "horiba_sdk.devices.device_manager": ModuleType(
            "horiba_sdk.devices.device_manager"
        ),
        "horiba_sdk.devices.single_devices": ModuleType(
            "horiba_sdk.devices.single_devices"
        ),
        "horiba_sdk.devices.single_devices.monochromator": ModuleType(
            "horiba_sdk.devices.single_devices.monochromator"
        ),
    }
    paths["horiba_sdk.core.acquisition_format"].AcquisitionFormat = Value
    paths["horiba_sdk.core.timer_resolution"].TimerResolution = Value
    paths["horiba_sdk.core.x_axis_conversion_type"].XAxisConversionType = Value
    paths["horiba_sdk.devices.device_manager"].DeviceManager = sdk.manager_factory
    paths[
        "horiba_sdk.devices.single_devices.monochromator"
    ].Monochromator = Monochromator
    for name, module in paths.items():
        monkeypatch.setitem(sys.modules, name, module)
        modules[name] = module

    source = Path(__file__).parents[1] / "src/labtools/devices/horiba_spectrometer.py"
    spec = importlib.util.spec_from_file_location("_fake_horiba_lifecycle", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)
        failure = sdk.failures.get("mono-delay")
        if failure is not None:
            raise failure

    module.asyncio = SimpleNamespace(sleep=sleep)
    return module.HoribaSpectrometer, sdk, sleeps


def run(awaitable):
    return asyncio.run(awaitable)


def test_success_start_disconnect_transcript_and_loop_identity(wrapper):
    cls, sdk, sleeps = wrapper

    async def scenario():
        device = cls()
        await device.connect()
        assert device.mono is sdk.mono and device.ccd is sdk.ccd
        await device.disconnect()
        await device.disconnect()
        return device

    device = run(scenario())
    assert sdk.events == [
        "manager-create",
        "manager-start",
        "mono-open",
        "mono-busy",
        "ccd-open",
        "ccd-busy",
        "ccd-configuration",
        "ccd-close",
        "mono-close",
        "manager-stop",
    ]
    assert sleeps == [1]
    assert len(set(sdk.thread_loop)) == 1
    assert device._teardown_started and not device._uncertain_handles
    with pytest.raises(RuntimeError, match="teardown"):
        run(device.connect())


@pytest.mark.parametrize(
    "stage,expected_cleanup",
    [
        ("manager-create", []),
        ("manager-start", ["manager-stop"]),
        ("mono-open", ["mono-close", "manager-stop"]),
        ("ccd-open", ["ccd-close", "mono-close", "manager-stop"]),
        ("ccd-configuration", ["ccd-close", "mono-close", "manager-stop"]),
    ],
)
@pytest.mark.parametrize("kind", [OSError, KeyboardInterrupt, asyncio.CancelledError])
def test_partial_startup_preserves_primary_and_cleans_every_acquired_handle(
    wrapper, stage, expected_cleanup, kind
):
    cls, sdk, _ = wrapper
    primary = kind(stage)
    sdk.failures[stage] = primary

    async def scenario():
        device = cls()
        with pytest.raises(kind) as caught:
            await device.connect()
        assert caught.value is primary
        return device

    device = run(scenario())
    cleanup = [
        event
        for event in sdk.events
        if event in {"ccd-close", "mono-close", "manager-stop"}
    ]
    assert cleanup == expected_cleanup
    assert device._teardown_started
    assert not device._uncertain_handles


@pytest.mark.parametrize(
    "failures",
    [
        {"ccd-close": OSError("ccd")},
        {"mono-close": OSError("mono")},
        {"manager-stop": OSError("manager")},
        {
            "ccd-close": OSError("ccd"),
            "mono-close": RuntimeError("mono"),
            "manager-stop": ValueError("manager"),
        },
    ],
)
def test_disconnect_attempts_all_stages_and_explicit_retry_only_uncertain(
    wrapper, failures
):
    cls, sdk, _ = wrapper
    sdk.failures.update(failures)

    async def scenario():
        device = cls()
        await device.connect()
        with pytest.raises(ExceptionGroup) as caught:
            await device.disconnect()
        assert list(caught.value.exceptions) == list(failures.values())
        assert caught.value._labtools_cleanup_failed is True
        assert set(device._uncertain_handles) == {
            name.split("-")[0] if name != "manager-stop" else "manager"
            for name in failures
        }
        with pytest.raises(RuntimeError, match="teardown"):
            await device.connect()
        with pytest.raises(RuntimeError, match="Connect"):
            await device.configure()
        before = list(sdk.events)
        sdk.failures.clear()
        await device.disconnect()
        retried = sdk.events[len(before) :]
        assert retried == [
            name
            for name in ("ccd-close", "mono-close", "manager-stop")
            if name in failures
        ]
        await device.disconnect()
        assert sdk.events[len(before) :] == retried
        return device

    device = run(scenario())
    assert not device._uncertain_handles


@pytest.mark.parametrize("kind", [KeyboardInterrupt, asyncio.CancelledError])
@pytest.mark.parametrize(
    "stage", ["ccd-close", "mono-delay", "mono-close", "manager-stop"]
)
def test_disconnect_keeps_interrupt_or_cancellation_primary(wrapper, kind, stage):
    cls, sdk, _ = wrapper
    primary = kind(stage)
    sdk.failures.update(
        {
            stage: primary,
            "manager-stop" if stage != "manager-stop" else "ccd-close": OSError(
                "other"
            ),
        }
    )

    async def scenario():
        device = cls()
        await device.connect()
        with pytest.raises(kind) as caught:
            await device.disconnect()
        assert caught.value is primary
        assert primary._horiba_cleanup_failures == (
            next(e for e in sdk.failures.values() if e is not primary),
        )
        assert primary._labtools_cleanup_failed is True

    run(scenario())
    expected = ["ccd-close"]
    if stage != "mono-delay":
        expected.append("mono-close")
    expected.append("manager-stop")
    assert [
        event
        for event in sdk.events
        if event in {"ccd-close", "mono-close", "manager-stop"}
    ][-3:] == expected[-3:]


@pytest.mark.parametrize("kind", [OSError, KeyboardInterrupt, asyncio.CancelledError])
def test_startup_primary_survives_cleanup_failure(wrapper, kind):
    cls, sdk, _ = wrapper
    primary = kind("open failed")
    cleanup = OSError("ccd close")
    sdk.failures.update(
        {"ccd-open": primary, "ccd-close": cleanup, "manager-stop": OSError("stop")}
    )

    async def scenario():
        device = cls()
        with pytest.raises(kind) as caught:
            await device.connect()
        assert caught.value is primary
        grouped = primary._horiba_cleanup_failures[0]
        assert grouped.exceptions == (cleanup, sdk.failures["manager-stop"])
        assert primary._labtools_cleanup_failed is True

    run(scenario())


def test_async_context_body_exception_survives_cleanup_group(wrapper):
    cls, sdk, _ = wrapper
    sdk.failures["ccd-close"] = OSError("close")
    primary = RuntimeError("body")

    async def scenario():
        with pytest.raises(RuntimeError) as caught:
            async with cls():
                raise primary
        assert caught.value is primary
        grouped = primary._horiba_cleanup_failures[0]
        assert grouped.exceptions == (sdk.failures["ccd-close"],)
        assert primary._labtools_cleanup_failed is True

    run(scenario())


def test_clean_context_exit_surfaces_cleanup_group(wrapper):
    cls, sdk, _ = wrapper
    sdk.failures["mono-close"] = OSError("mono close")

    async def scenario():
        with pytest.raises(ExceptionGroup) as caught:
            async with cls():
                pass
        assert caught.value.exceptions == (sdk.failures["mono-close"],)

    run(scenario())


def test_duplicate_connect_refused_without_second_manager(wrapper):
    cls, sdk, _ = wrapper

    async def scenario():
        device = cls()
        await device.connect()
        with pytest.raises(RuntimeError, match="already started"):
            await device.connect()
        await device.disconnect()

    run(scenario())
    assert sdk.events.count("manager-create") == 1


def test_identity_failure_cleans_all_opened_handles(wrapper):
    cls, sdk, _ = wrapper
    sdk.configuration["serialNumber"] = "wrong"

    async def scenario():
        device = cls()
        with pytest.raises(RuntimeError, match="Detector does not match"):
            await device.connect()
        return device

    device = run(scenario())
    assert sdk.events[-3:] == ["ccd-close", "mono-close", "manager-stop"]
    assert device._teardown_started and not device._uncertain_handles


def test_real_wrapper_cleanup_failure_reaches_worker_fault_contract(wrapper):
    from labtools.acquisition.alignment_spectrum import AlignmentSettings
    from labtools.acquisition.spectrum_service import SpectrumService
    from labtools.runtime.spectrum_backend import open_real_alignment
    from labtools.runtime.spectrum_worker import SpectrumWorker

    cls, sdk, _ = wrapper
    device = cls()

    async def configure(**kwargs):
        assert kwargs["exposure_time"] >= 0.065

    async def set_wavelength(value):
        return value

    async def get_spectrum(**kwargs):
        return np.array([700.0]), np.array([5.0])

    device.configure = configure
    device.set_wavelength = set_wavelength
    device.get_spectrum = get_spectrum
    sdk.failures["ccd-close"] = OSError("real wrapper close failed")

    def factory(**kwargs):
        assert kwargs == {"preset": "syncerity"}
        return device

    service = SpectrumService(
        lambda settings: None,
        lambda settings: open_real_alignment(settings, spectrometer_factory=factory),
    )
    worker = SpectrumWorker(service, backend="real")
    try:
        job = worker.acquire_alignment(AlignmentSettings("w2-real-wrapper"))
        with pytest.raises(ExceptionGroup, match="HORIBA SDK cleanup failed"):
            job.result(3)
        assert worker.status().state == "faulted"
        assert sdk.events[-3:] == ["ccd-close", "mono-close", "manager-stop"]
    finally:
        sdk.failures.clear()
        device._uncertain_handles.clear()
        worker.close()
    assert not worker.is_alive()


@pytest.mark.parametrize(
    "cleanup_kind", [OSError, KeyboardInterrupt, asyncio.CancelledError]
)
def test_backend_preserves_operation_primary_when_disconnect_fails(cleanup_kind):
    from labtools.acquisition.alignment_spectrum import AlignmentSettings
    from labtools.runtime.spectrum_backend import open_real_alignment

    primary = RuntimeError("capture failed")
    cleanup = cleanup_kind("disconnect failed")

    class Spectrometer:
        async def connect(self):
            pass

        async def configure(self, **kwargs):
            pass

        async def set_wavelength(self, value):
            return value

        async def get_spectrum(self, **kwargs):
            raise primary

        async def disconnect(self):
            raise cleanup

    async def scenario():
        with pytest.raises(RuntimeError) as caught:
            async with open_real_alignment(
                AlignmentSettings("w2-backend-primary"),
                spectrometer_factory=lambda **kwargs: Spectrometer(),
            ) as backend:
                await backend.capture(False)
        assert caught.value is primary
        assert primary._horiba_cleanup_failures == (cleanup,)
        assert primary._labtools_cleanup_failed is True

    run(scenario())
