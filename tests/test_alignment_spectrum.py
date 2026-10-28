"""Alignment uses SpectrumService and SpectrumWorker, without a parallel path."""

import asyncio
from contextlib import asynccontextmanager
from threading import get_ident

import numpy as np
import pytest

from labtools.acquisition.alignment_spectrum import AlignmentResult, AlignmentSettings
from labtools.acquisition.spectrum_service import SpectrumService
from labtools.runtime.spectrum_worker import SpectrumWorker, SpectrumWorkerBusyError


@pytest.fixture
def settings():
    return AlignmentSettings("alignment-test", exposure_s=0.1, backend="real")


def test_alignment_service_result_identity(settings):
    events = []

    @asynccontextmanager
    async def factory(request):
        events.append(("open", get_ident(), id(asyncio.get_running_loop())))

        class Backend:
            actual_centre_nm = 690.2

            async def capture(self, subtract):
                events.append(
                    ("capture", get_ident(), id(asyncio.get_running_loop()), subtract)
                )
                return (
                    np.array([691.0, 690.0]),
                    np.array([5.0, 3.0]),
                    np.array([6.0, 4.0]),
                )

        yield Backend()
        events.append(("close", get_ident(), id(asyncio.get_running_loop())))

    worker = SpectrumWorker(SpectrumService(lambda s: None, factory), backend="real")
    result = worker.acquire_alignment(settings).result(3)
    assert isinstance(result, AlignmentResult)
    np.testing.assert_array_equal(result.intensity, [5, 3])
    np.testing.assert_array_equal(result.raw_intensity, [6, 4])
    assert len({(e[1], e[2]) for e in events}) == 1
    assert events[-1][0] == "close"
    worker.close()


def test_alignment_busy_rejected_without_second_backend(settings):
    import threading

    entered, release = threading.Event(), threading.Event()
    opens = []

    @asynccontextmanager
    async def factory(request):
        opens.append(1)
        entered.set()

        class Backend:
            actual_centre_nm = 690

            async def capture(self, subtract):
                while not release.is_set():
                    await asyncio.sleep(0.002)
                return np.array([1.0]), np.array([2.0]), np.array([2.0])

        yield Backend()

    worker = SpectrumWorker(SpectrumService(lambda s: None, factory), backend="real")
    first = worker.acquire_alignment(settings, owner="spectrum-alignment")
    assert entered.wait(2)
    with pytest.raises(SpectrumWorkerBusyError, match="spectrum-alignment"):
        worker.acquire_alignment(settings, owner="ordinary-spectrum")
    release.set()
    first.result(3)
    assert len(opens) == 1
    worker.close()


def test_detector_preset_exposure_minima():
    sync = {
        "gains": (("gain", 2),),
        "speeds": (("speed", 0),),
        "minimum_exposure_s": 0.065,
    }
    symphony = {
        "gains": (("gain", 2),),
        "speeds": (("speed", 0),),
        "minimum_exposure_s": 0.1,
    }

    with pytest.raises(ValueError, match="at least 0.065"):
        AlignmentSettings(
            "test",
            preset="syncerity",
            exposure_s=0.064,
        ).validate_detector(sync)

    with pytest.raises(ValueError, match="at least 0.1"):
        AlignmentSettings(
            "test",
            preset="symphony",
            exposure_s=0.099,
        ).validate_detector(symphony)

    AlignmentSettings(
        "test",
        preset="syncerity",
        exposure_s=0.065,
    ).validate_detector(sync)

    AlignmentSettings(
        "test",
        preset="symphony",
        exposure_s=0.1,
    ).validate_detector(symphony)
