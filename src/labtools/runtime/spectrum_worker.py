"""Lazy dedicated asyncio-loop worker for serialized SpectrumService jobs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from dataclasses import dataclass
from threading import Event, RLock, Thread, get_ident
from typing import Any

from labtools.acquisition.spectrum_service import SpectrumService


class SpectrumWorkerBusyError(RuntimeError):
    """Expected conflict when a spectrum job already owns the worker."""


class SpectrumWorkerFaultedError(RuntimeError):
    """Normal jobs are rejected after a real backend operation fails."""


@dataclass(frozen=True)
class SpectrumWorkerStatus:
    state: str
    owner: str | None
    job: str | None
    thread_id: int | None
    backend: str


class SpectrumJob:
    """Thread-safe result and cooperative job-boundary cancellation handle."""

    def __init__(self, future: Future, cancel_event: Event) -> None:
        self._future = future
        self._cancel_event = cancel_event

    def cancel(self) -> bool:
        if self._future.done():
            return False
        self._cancel_event.set()
        return True

    def result(self, timeout: float | None = None):
        return self._future.result(timeout)

    def done(self) -> bool:
        return self._future.done()


class SpectrumWorker:
    """Own one lazy thread/loop and reject concurrent complete service jobs.

    Cancellation is cooperative at the existing SpectrumService boundaries: before
    opening and after one complete backend operation. It does not interrupt an SDK
    call. The job remains busy until service/context cleanup has completed.
    """

    def __init__(self, service: SpectrumService, *, backend: str) -> None:
        if backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        self._service = service
        self._backend = backend
        self._lock = RLock()
        self._state = "unopened"
        self._owner = None
        self._job = None
        self._thread: Thread | None = None
        self._thread_id: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = Event()
        self._active: Future | None = None

    def status(self) -> SpectrumWorkerStatus:
        with self._lock:
            return SpectrumWorkerStatus(
                self._state, self._owner, self._job, self._thread_id, self._backend
            )

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop
            self._thread_id = get_ident()
            if self._state == "starting":
                self._state = "available"
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.close()

    def _ensure_started(self) -> None:
        with self._lock:
            if self._state == "unopened":
                self._state = "starting"
                self._ready.clear()
                self._thread = Thread(
                    target=self._thread_main,
                    name="labtools-spectrum-worker",
                    daemon=False,
                )
                self._thread.start()
            elif self._state in {"closing", "closed"}:
                raise RuntimeError(f"Spectrum worker is {self._state}")
        self._ready.wait()

    def _submit(
        self,
        owner: str,
        job: str,
        operation: Callable[[Callable[[], bool]], Coroutine[Any, Any, Any]],
    ) -> SpectrumJob:
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("Provide a nonempty spectrum owner")
        if not isinstance(job, str) or not job.strip():
            raise ValueError("Provide a nonempty spectrum job label")
        self._ensure_started()
        cancel_event = Event()
        result_future: Future = Future()
        with self._lock:
            if self._state == "faulted":
                raise SpectrumWorkerFaultedError("Spectrum worker is faulted")
            if self._state != "available":
                raise SpectrumWorkerBusyError(
                    f"Spectrum worker is {self._state}; owner={self._owner!r}, job={self._job!r}"
                )
            self._state, self._owner, self._job = "busy", owner, job
            loop = self._loop

        async def run() -> None:
            value = None
            failure: BaseException | None = None
            cancelled = False
            try:
                value = await operation(cancel_event.is_set)
            except asyncio.CancelledError as exc:
                failure = exc
                cancelled = True
            except BaseException as exc:  # noqa: BLE001 - preserve job failure after state cleanup
                failure = exc
            with self._lock:
                if failure is None or cancelled or self._backend == "simulation":
                    self._state = "available"
                else:
                    self._state = "faulted"
                self._owner = self._job = None
                self._active = None
            # Publish completion only after ownership/state has been updated.
            if failure is None:
                result_future.set_result(value)
            else:
                result_future.set_exception(failure)

        assert loop is not None
        active = asyncio.run_coroutine_threadsafe(run(), loop)
        with self._lock:
            self._active = active
        return SpectrumJob(result_future, cancel_event)

    def test_connection(self, settings, *, owner="spectrum") -> SpectrumJob:
        return self._submit(
            owner,
            "test-connection",
            lambda cancelled: self._service.test_connection(
                settings, cancel_requested=cancelled
            ),
        )

    def capture_dark(self, settings, *, owner="spectrum") -> SpectrumJob:
        return self._submit(
            owner,
            "capture-dark",
            lambda cancelled: self._service.capture_dark(
                settings, cancel_requested=cancelled
            ),
        )

    def acquire(
        self, settings, *, owner="spectrum", dark_mode="none", dark=None
    ) -> SpectrumJob:
        return self._submit(
            owner,
            "acquire",
            lambda cancelled: self._service.acquire(
                settings,
                dark_mode=dark_mode,
                dark=dark,
                cancel_requested=cancelled,
            ),
        )

    def acquire_alignment(self, settings, *, owner="spectrum-alignment") -> SpectrumJob:
        return self._submit(
            owner,
            "alignment-frame",
            lambda cancelled: self._service.acquire_alignment(
                settings, cancel_requested=cancelled
            ),
        )

    def close(self) -> None:
        with self._lock:
            if self._state == "closed":
                return
            if self._state == "busy":
                raise SpectrumWorkerBusyError(
                    f"Spectrum worker busy; owner={self._owner!r}, job={self._job!r}"
                )
            self._state = "closing"
            loop, thread = self._loop, self._thread
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join()
        with self._lock:
            self._loop = None
            self._thread = None
            self._thread_id = None
            self._state = "closed"

    def is_alive(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()
