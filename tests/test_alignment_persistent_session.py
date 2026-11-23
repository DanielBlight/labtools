"""Continuous ownership regression tests, independent of Qt and native SDKs."""

import asyncio
import time
from contextlib import asynccontextmanager
from threading import Event, get_ident

import numpy as np
import pytest

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.acquisition.spectrum_service import SpectrumService
from labtools.runtime.spectrum_backend import open_real_alignment
from labtools.runtime.spectrum_worker import (
    SpectrumWorker,
    SpectrumWorkerBusyError,
    SpectrumWorkerFaultedError,
)


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("Timed out waiting for alignment lifecycle")
        time.sleep(0.001)


class Session:
    def __init__(self, failure=None):
        self.events = []
        self.frames = 0
        self.failure = failure
        self.release = Event()
        self.cleaning = Event()
        self.allow_cleanup = Event()

    def record(self, name):
        self.events.append((name, get_ident(), id(asyncio.get_running_loop())))

    @asynccontextmanager
    async def open(self, settings):
        self.record("connect")
        try:
            self.record("configure")
            self.record("move")
            if self.failure == "connect":
                raise OSError("connect failed")
            parent = self

            class Backend:
                actual_centre_nm = settings.centre_nm

                async def capture(self, subtract_dark):
                    while not parent.release.is_set():
                        await asyncio.sleep(0.001)
                    parent.frames += 1
                    if parent.failure == "capture" and parent.frames >= 3:
                        raise OSError("capture failed")
                    if subtract_dark:
                        parent.record("dark")
                    parent.record("capture")
                    return [690.0], [4.0], [5.0]

            yield Backend()
        finally:
            self.cleaning.set()
            while not self.allow_cleanup.is_set():
                await asyncio.sleep(0.001)
            self.record("disconnect")
            if self.failure == "disconnect":
                raise OSError("disconnect failed")


def worker_for(session):
    return SpectrumWorker(SpectrumService(lambda s: None, session.open), backend="real")


def test_many_frames_one_session_busy_through_stop_cleanup_and_restart():
    session = Session()
    worker = worker_for(session)
    job = worker.start_alignment(AlignmentSettings("test", subtract_dark=True))
    try:
        session.release.set()
        wait_for(lambda: session.frames >= 12)
        assert worker.status().owner == "spectrum-alignment"
        with pytest.raises(SpectrumWorkerBusyError):
            worker.acquire_alignment(AlignmentSettings("test"), owner="other")
        with pytest.raises(SpectrumWorkerBusyError):
            worker.start_alignment(AlignmentSettings("test"), owner="second")
        with pytest.raises(SpectrumWorkerBusyError):
            worker.close()
        job.cancel()
        wait_for(session.cleaning.is_set)
        assert not job.done() and worker.status().state == "busy"
        assert [e[0] for e in session.events].count("connect") == 1
        latest = job.take_latest()
        assert latest[0] >= 12
        assert latest[1].dark_subtracted
        assert not latest[1].intensity.flags.writeable
        assert job.take_latest() is None
        session.allow_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            job.result(5)
        names = [e[0] for e in session.events]
        for name in ("connect", "configure", "move", "disconnect"):
            assert names.count(name) == 1
        assert names.count("dark") == names.count("capture")
        assert len({e[1:] for e in session.events}) == 1
        assert worker.status().state == "available"
        second = worker.start_alignment(AlignmentSettings("test"))
        wait_for(lambda: [e[0] for e in session.events].count("connect") == 2)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            second.result(5)
        assert [e[0] for e in session.events].count("disconnect") == 2
    finally:
        session.release.set()
        session.allow_cleanup.set()
        job.cancel()
        wait_for(lambda: worker.status().state != "busy")
        worker.close()


@pytest.mark.parametrize("failure", ["connect", "capture", "disconnect"])
def test_stream_failure_faults_only_after_cleanup(failure):
    session = Session(failure)
    session.release.set()
    worker = worker_for(session)
    job = worker.start_alignment(AlignmentSettings("test"))
    try:
        if failure == "disconnect":
            wait_for(lambda: session.frames >= 3)
            job.cancel()
        wait_for(session.cleaning.is_set)
        assert worker.status().state == "busy" and not job.done()
        session.allow_cleanup.set()
        with pytest.raises(OSError, match=failure):
            job.result(5)
        assert worker.status().state == "faulted"
        with pytest.raises(SpectrumWorkerFaultedError):
            worker.start_alignment(AlignmentSettings("test"))
    finally:
        session.allow_cleanup.set()
        wait_for(job.done)
        worker.close()


def test_real_adapter_reuses_connection_and_guards_separate_clients():
    calls = []

    class Spec:
        def __init__(self, **kwargs):
            calls.append("construct")

        async def connect(self):
            calls.append("connect")

        async def configure(self, **kwargs):
            calls.append("configure")

        async def set_wavelength(self, value):
            calls.append("move")
            return value

        async def get_spectrum(self, **kwargs):
            calls.append("capture")
            return np.array([690.0]), np.array([5.0])

        async def disconnect(self):
            calls.append("disconnect")

    async def run():
        settings = AlignmentSettings("test")
        async with open_real_alignment(settings, spectrometer_factory=Spec) as backend:
            for _ in range(5):
                await backend.capture(False)
            with pytest.raises(RuntimeError, match="already owned"):
                async with open_real_alignment(settings, spectrometer_factory=Spec):
                    pytest.fail("Second client acquired owned hardware")
        async with open_real_alignment(settings, spectrometer_factory=Spec):
            pass

    asyncio.run(run())
    assert calls.count("construct") == 2
    assert calls.count("connect") == calls.count("configure") == calls.count("move") == 2
    assert calls.count("capture") == 5
    assert calls.count("disconnect") == 2


def test_invalid_stream_request_does_not_start_worker_or_open_backend():
    session = Session()
    worker = worker_for(session)
    try:
        with pytest.raises(ValueError):
            worker.start_alignment(AlignmentSettings("test", exposure_s=0.001))
        with pytest.raises(ValueError, match="backend"):
            worker.start_alignment(AlignmentSettings("test", backend="simulation"))
        assert worker.status().state == "unopened"
        assert not session.events
    finally:
        worker.close()


def test_simulated_stream_never_imports_native_horiba(monkeypatch):
    import builtins

    from labtools.runtime.spectrum_backend import create_spectrum_service

    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("horiba_sdk", "labtools.devices.horiba_spectrometer")):
            raise AssertionError("Native import in simulated alignment")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    worker = SpectrumWorker(create_spectrum_service(backend="simulation"), backend="simulation")
    job = worker.start_alignment(AlignmentSettings("test", backend="simulation"))
    try:
        wait_for(lambda: job.take_latest() is not None)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            job.result(5)
        assert worker.status().state == "available"
    finally:
        job.cancel()
        wait_for(job.done)
        worker.close()


def test_real_adapter_constructor_failure_releases_guard():
    from labtools.runtime.spectrum_backend import _REAL_RANGE_OWNERSHIP

    def broken(**kwargs):
        raise OSError("constructor failed")

    async def run():
        with pytest.raises(OSError, match="constructor"):
            async with open_real_alignment(AlignmentSettings("test"), spectrometer_factory=broken):
                pytest.fail("Constructor unexpectedly succeeded")
        assert _REAL_RANGE_OWNERSHIP.acquire(blocking=False)
        _REAL_RANGE_OWNERSHIP.release()

    asyncio.run(run())
