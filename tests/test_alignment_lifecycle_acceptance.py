"""Deterministic blocked-backend acceptance; no Qt or physical instrument required."""

import asyncio
from contextlib import asynccontextmanager
from threading import Event, get_ident

import numpy as np
import pytest

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.acquisition.spectrum_service import SpectrumService
from labtools.runtime.spectrum_worker import (
    SpectrumWorker,
    SpectrumWorkerBusyError,
    SpectrumWorkerFaultedError,
)


class BlockedBackend:
    def __init__(self, failure=None):
        self.failure = failure
        self.entered = Event()
        self.release = Event()
        self.cleaning = Event()
        self.cleaned = Event()
        self.release_cleanup = Event()
        self.events = []
        self.requests = []

    def record(self, label):
        self.events.append((label, get_ident(), id(asyncio.get_running_loop())))

    async def wait(self, event):
        while not event.is_set():
            await asyncio.sleep(0.001)

    @asynccontextmanager
    async def open(self, settings):
        primary = None
        self.requests.append(settings)
        try:
            for stage in ("connect", "configure", "move"):
                self.record(stage)
                if self.failure == stage:
                    raise OSError(f"injected {stage}")
            parent = self

            class Backend:
                actual_centre_nm = settings.centre_nm

                async def capture(self, subtract_dark):
                    parent.entered.set()
                    await parent.wait(parent.release)
                    if subtract_dark:
                        parent.record("dark")
                        if parent.failure == "dark":
                            raise OSError("injected dark")
                    parent.record("capture")
                    if parent.failure == "capture":
                        raise OSError("injected capture")
                    return np.array([690.0]), np.array([4.0]), np.array([5.0])

            yield Backend()
        except BaseException as exc:
            primary = exc
            raise
        finally:
            self.record("cleanup-start")
            self.cleaning.set()
            await self.wait(self.release_cleanup)
            self.record("disconnect")
            self.cleaned.set()
            if self.failure == "disconnect":
                error = OSError("injected disconnect")
                if primary is None:
                    raise error
                primary.add_note(str(error))
                primary._labtools_cleanup_failed = True

    def unblock(self):
        self.release.set()
        self.release_cleanup.set()


def make_worker(backend):
    return SpectrumWorker(
        SpectrumService(lambda settings: None, backend.open), backend="real"
    )


def test_cancel_retains_busy_through_cleanup_then_allows_restart():
    backend = BlockedBackend()
    worker = make_worker(backend)
    try:
        job = worker.acquire_alignment(AlignmentSettings("test"))
        assert backend.entered.wait(3)
        job.cancel()
        backend.release.set()
        assert backend.cleaning.wait(3)
        assert not job.done()
        assert worker.status().state == "busy"
        with pytest.raises(SpectrumWorkerBusyError):
            worker.acquire_alignment(AlignmentSettings("test"), owner="other")
        with pytest.raises(SpectrumWorkerBusyError):
            worker.close()
        backend.release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            job.result(3)
        assert backend.cleaned.is_set()
        assert worker.status().state == "available"
        result = worker.acquire_alignment(AlignmentSettings("test")).result(3)
        np.testing.assert_array_equal(result.raw_intensity, [5.0])
        assert len({event[1:] for event in backend.events}) == 1
    finally:
        backend.unblock()
        if worker.status().state == "busy":
            job.result(3)
        worker.close()
    assert not worker.is_alive()


@pytest.mark.parametrize(
    "failure", ["connect", "configure", "move", "dark", "capture", "disconnect"]
)
def test_failure_cleanup_finishes_before_fault_is_published(failure):
    backend = BlockedBackend(failure)
    worker = make_worker(backend)
    job = None
    try:
        job = worker.acquire_alignment(AlignmentSettings("test", subtract_dark=True))
        backend.release.set()
        assert backend.cleaning.wait(3)
        assert worker.status().state == "busy"
        assert not job.done()
        backend.release_cleanup.set()
        with pytest.raises(OSError, match=failure):
            job.result(3)
        assert worker.status().state == "faulted"
        assert backend.cleaned.is_set()
        with pytest.raises(SpectrumWorkerFaultedError):
            worker.acquire_alignment(AlignmentSettings("test"))
    finally:
        backend.unblock()
        if job is not None:
            try:
                job.result(3)
            except OSError:
                pass
        worker.close()
    assert not worker.is_alive()
