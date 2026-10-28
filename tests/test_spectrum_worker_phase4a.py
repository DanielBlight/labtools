"""Persistent spectrum worker contracts with no native HORIBA dependency."""

from __future__ import annotations

import asyncio
import builtins
from concurrent.futures import TimeoutError
from dataclasses import replace
from threading import Event, get_ident

import numpy as np
import pytest

from labtools.acquisition.spectrum_service import DarkRecord, SpectrumResult
from labtools.config.spectrum import SpectrumSettings
from labtools.runtime.spectrum_worker import (
    SpectrumWorker,
    SpectrumWorkerBusyError,
    SpectrumWorkerFaultedError,
)


@pytest.fixture
def settings():
    return SpectrumSettings(
        "test-worker-v1",
        "syncerity",
        0.1,
        2,
        0,
        0.5,
        500.0,
        600.0,
        backend="real",
    )


class FakeService:
    def __init__(self, *, entered=None, release=None, failure=None):
        self.events = []
        self.entered = entered
        self.release = release
        self.failure = failure

    async def _run(self, name, settings, cancel_requested):
        loop = id(asyncio.get_running_loop())
        thread = get_ident()
        self.events.append((name + ":start", thread, loop))
        if self.entered:
            self.entered.set()
        if self.release:
            while not self.release.is_set():
                await asyncio.sleep(0.002)
        if cancel_requested():
            self.events.append(
                (name + ":cancel-cleanup", get_ident(), id(asyncio.get_running_loop()))
            )
            raise asyncio.CancelledError()
        if self.failure == name:
            raise OSError("injected " + name)
        self.events.append(
            (name + ":finish", get_ident(), id(asyncio.get_running_loop()))
        )
        x = np.array([500.0, 600.0])
        y = np.array([1.0, 2.0])
        if name == "dark":
            return DarkRecord(settings, x, y, "dark", "2026-10-28T00:00:00+00:00")
        if name == "acquire":
            return SpectrumResult(settings, x, y, y, "none", None)
        return None

    async def test_connection(self, settings, *, cancel_requested=None):
        return await self._run("test", settings, cancel_requested)

    async def capture_dark(self, settings, *, cancel_requested=None):
        return await self._run("dark", settings, cancel_requested)

    async def acquire(
        self, settings, *, dark_mode="none", dark=None, cancel_requested=None
    ):
        return await self._run("acquire", settings, cancel_requested)


def test_lazy_one_thread_loop_sequential_jobs(settings):
    service = FakeService()
    worker = SpectrumWorker(service, backend="real")
    assert worker.status().state == "unopened" and not worker.is_alive()
    worker.test_connection(settings).result(3)
    dark = worker.capture_dark(settings).result(3)
    result = worker.acquire(settings).result(3)
    assert isinstance(dark, DarkRecord) and isinstance(result, SpectrumResult)
    identities = {(event[1], event[2]) for event in service.events}
    assert len(identities) == 1 and next(iter(identities))[0] != get_ident()
    assert worker.status().state == "available"
    worker.close()
    worker.close()
    assert worker.status().state == "closed" and not worker.is_alive()


def test_busy_is_recoverable_and_rejects_second_job(settings):
    entered, release = Event(), Event()
    service = FakeService(entered=entered, release=release)
    worker = SpectrumWorker(service, backend="real")
    first = worker.acquire(settings, owner="ordinary-gui")
    assert entered.wait(2)
    status = worker.status()
    assert status.state == "busy" and status.owner == "ordinary-gui"
    with pytest.raises(SpectrumWorkerBusyError, match="ordinary-gui"):
        worker.capture_dark(settings, owner="alignment")
    assert len([e for e in service.events if e[0].endswith(":start")]) == 1
    release.set()
    first.result(3)
    worker.capture_dark(settings).result(3)
    worker.close()


def test_cancellation_is_boundary_cooperative_and_cleanup_precedes_available(settings):
    entered, release = Event(), Event()
    service = FakeService(entered=entered, release=release)
    worker = SpectrumWorker(service, backend="real")
    job = worker.acquire(settings)
    assert entered.wait(2)
    assert job.cancel()
    assert worker.status().state == "busy"
    with pytest.raises(TimeoutError):
        job.result(0.02)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        job.result(3)
    assert worker.status().state == "available"
    assert any(e[0] == "acquire:cancel-cleanup" for e in service.events)
    worker.close()


def test_real_failure_faults_and_blocks_reuse(settings):
    service = FakeService(failure="acquire")
    worker = SpectrumWorker(service, backend="real")
    with pytest.raises(OSError, match="injected acquire"):
        worker.acquire(settings).result(3)
    assert worker.status().state == "faulted"
    with pytest.raises(SpectrumWorkerFaultedError):
        worker.test_connection(settings)
    assert len(service.events) == 1
    worker.close()
    assert not worker.is_alive()


def test_simulation_failure_does_not_claim_real_resource_fault(settings):
    service = FakeService(failure="acquire")
    worker = SpectrumWorker(service, backend="simulation")
    synthetic = replace(settings, backend="simulation")
    with pytest.raises(OSError):
        worker.acquire(synthetic).result(3)
    assert worker.status().state == "available"
    worker.close()


def test_import_and_construction_are_native_free(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("horiba_sdk", "horiba", "icl")):
            raise AssertionError("native HORIBA import")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    worker = SpectrumWorker(FakeService(), backend="real")
    assert worker.status().state == "unopened"
    worker.close()
