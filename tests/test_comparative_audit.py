"""Regression tests for the baseline-to-current lifecycle audit; no hardware."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import pytest

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.config.horiba_presets import detector_options
from labtools.runtime.idq_count_service import IDQCountService
from labtools.runtime.spectrum_backend import (
    create_spectrum_service,
    open_real_alignment,
)
from labtools.runtime.spectrum_worker import SpectrumWorker
from labtools.simulation.spectrum import open_simulated_alignment


@pytest.mark.parametrize("preset,minimum", [("syncerity", 0.065), ("symphony", 0.1)])
def test_alignment_minimum_is_enforced_without_gui(preset, minimum):
    with pytest.raises(ValueError, match="at least"):
        AlignmentSettings("audit", preset=preset, exposure_s=minimum - 0.001).validate()
    AlignmentSettings("audit", preset=preset, exposure_s=minimum).validate()
    options = detector_options(preset)
    assert options["minimum_exposure_s"] == minimum
    options["minimum_exposure_s"] = 0
    assert detector_options(preset)["minimum_exposure_s"] == minimum


def test_alignment_backend_mismatch_rejected_before_factory():
    calls = []

    async def check():
        with pytest.raises(ValueError, match="refuses"):
            async with open_real_alignment(
                AlignmentSettings("audit", backend="simulation"),
                spectrometer_factory=lambda **kw: calls.append(kw),
            ):
                pytest.fail("must not yield")
        with pytest.raises(ValueError, match="refuses"):
            async with open_simulated_alignment(AlignmentSettings("audit")):
                pytest.fail("must not yield")

    asyncio.run(check())
    assert calls == []


def test_worker_backend_mismatch_does_not_start_thread():
    worker = SpectrumWorker(
        create_spectrum_service(backend="simulation"), backend="simulation"
    )
    try:
        with pytest.raises(ValueError, match="backend"):
            worker.acquire_alignment(AlignmentSettings("audit", backend="real"))
        assert not worker.is_alive()
        assert worker.status().state == "unopened"
    finally:
        worker.close()


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_idq_partial_connect_failure_attempts_cleanup(cleanup_fails):
    events = []
    primary = OSError("connect failed")

    class Controller:
        def __init__(self, address):
            events.append(address)

        def connect(self):
            raise primary

        def disconnect(self):
            events.append("disconnect")
            if cleanup_fails:
                raise OSError("close failed")

    with pytest.raises(OSError, match="connect failed") as caught:
        IDQCountService("169.254.99.159", controller_factory=Controller)
    assert caught.value is primary
    assert events == ["169.254.99.159", "disconnect"]
    if cleanup_fails:
        assert "close failed" in str(primary.__notes__)


def test_close_during_worker_start_does_not_leave_thread(monkeypatch):
    entered, release = Event(), Event()
    original = asyncio.new_event_loop

    def delayed_loop():
        entered.set()
        assert release.wait(3)
        return original()

    monkeypatch.setattr(asyncio, "new_event_loop", delayed_loop)
    worker = SpectrumWorker(
        create_spectrum_service(backend="simulation"), backend="simulation"
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        submit = pool.submit(
            worker.acquire_alignment, AlignmentSettings("audit", backend="simulation")
        )
        assert entered.wait(2)
        close = pool.submit(worker.close)
        # close marks closing before the delayed loop becomes available.
        import time

        deadline = time.monotonic() + 2
        while worker.status().state != "closing":
            assert time.monotonic() < deadline
            time.sleep(0.001)
        release.set()
        with pytest.raises(RuntimeError):
            submit.result(3)
        close.result(3)
    assert worker.status().state == "closed"
    assert not worker.is_alive()
    worker.close()


def test_worker_loop_startup_failure_is_reported(monkeypatch):
    def fail():
        raise OSError("loop startup failed")

    monkeypatch.setattr(asyncio, "new_event_loop", fail)
    worker = SpectrumWorker(
        create_spectrum_service(backend="simulation"), backend="simulation"
    )
    try:
        with pytest.raises(RuntimeError, match="startup failed"):
            worker.acquire_alignment(AlignmentSettings("audit", backend="simulation"))
    finally:
        worker.close()
    assert not worker.is_alive()


def test_shared_counter_failure_limit_is_per_map():
    from labtools.config.intensity_map import IntensityMapConfig
    from labtools.simulation.map_devices import SimulatedMapState
    from labtools.simulation.shared_map import synthetic_counter_provider

    state = SimulatedMapState(measurements=20, gate_open=True)
    config = replace(
        IntensityMapConfig(0, 1, 2, 0, 1, 2),
        backend="simulation",
        simulation_realtime=False,
        simulation_fail_after_points=1,
    )
    provider = synthetic_counter_provider(state)
    for _ in range(2):
        with provider(config) as counter:
            counter.configure_channel(1, threshold_v=0.1, edge="rising")
            counter.get_simultaneous_counts((1,), 0.01)
            with pytest.raises(TimeoutError):
                counter.get_simultaneous_counts((1,), 0.01)


def test_native_free_preset_values_match_wrapper_source():
    import ast
    from pathlib import Path

    source = Path(__file__).parents[1] / "src/labtools/devices/horiba_spectrometer.py"
    tree = ast.parse(source.read_text())
    cls = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "HoribaSpectrometer"
    )
    presets = next(
        n
        for n in cls.body
        if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "PRESETS"
    )
    for key, value in zip(presets.value.keys, presets.value.values, strict=True):
        name = ast.literal_eval(key)
        spreads = [
            v for k, v in zip(value.keys, value.values, strict=True) if k is None
        ]
        assert len(spreads) == 1
        assert spreads[0].func.id == "detector_options"
        assert ast.literal_eval(spreads[0].args[0]) == name


def test_cancelled_real_alignment_with_failed_disconnect_faults_worker():
    from contextlib import asynccontextmanager
    from functools import partial

    import numpy as np

    from labtools.acquisition.spectrum_service import SpectrumService

    entered, release = Event(), Event()

    class Spectrometer:
        def __init__(self, **kwargs):
            pass

        async def connect(self):
            pass

        async def configure(self, **kwargs):
            assert "minimum_exposure_override_s" not in kwargs

        async def set_wavelength(self, centre):
            return centre

        async def get_spectrum(self, **kwargs):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.001)
            return np.array([1.0]), np.array([2.0])

        async def disconnect(self):
            raise OSError("disconnect failed")

    @asynccontextmanager
    async def unused(settings):
        pytest.fail("range path must not run")
        yield

    service = SpectrumService(
        unused, partial(open_real_alignment, spectrometer_factory=Spectrometer)
    )
    worker = SpectrumWorker(service, backend="real")
    try:
        job = worker.acquire_alignment(AlignmentSettings("audit"))
        assert entered.wait(2)
        job.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError) as caught:
            job.result(3)
        assert "disconnect failed" in str(caught.value.__notes__)
        assert worker.status().state == "faulted"
    finally:
        release.set()
        worker.close()
