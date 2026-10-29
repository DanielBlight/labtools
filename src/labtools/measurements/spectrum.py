"""Stable Qt-free spectrum measurement facade over SpectrumService/Worker."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from labtools.acquisition.spectrum_service import (
    DarkRecord,
    SpectrumResult,
    SpectrumService,
)
from labtools.config.spectrum import SpectrumSettings
from labtools.runtime.spectrum_backend import create_spectrum_service
from labtools.runtime.spectrum_worker import SpectrumJob, SpectrumWorker

Progress = Callable[[str], None]


@dataclass(frozen=True)
class SpectrumRequest:
    settings: SpectrumSettings
    dark_mode: str = "none"
    dark: DarkRecord | None = None
    owner: str = "scripted-spectrum"

    def validate(self) -> None:
        self.settings.validate()
        if self.dark_mode not in {"none", "per_center", "per_frame", "pre_taken"}:
            raise ValueError("Unknown dark mode")
        if self.dark_mode == "pre_taken" and self.dark is None:
            raise ValueError("pre_taken requires a DarkRecord")
        if self.dark_mode != "pre_taken" and self.dark is not None:
            raise ValueError("DarkRecord is only valid for pre_taken mode")
        if not self.owner.strip():
            raise ValueError("owner must be nonempty")


@dataclass(frozen=True)
class MeasurementProvenance:
    backend: str
    configuration_id: str
    synthetic: bool


@dataclass(frozen=True)
class SpectrumMeasurement:
    result: SpectrumResult
    provenance: MeasurementProvenance


class SpectrumRuntime:
    """Explicit owner of one service and optional worker; Qt/native imports stay lazy."""

    def __init__(self, *, backend: str, service: SpectrumService | None = None) -> None:
        if backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        self.backend = backend
        self.service = service or create_spectrum_service(backend=backend)
        self._worker: SpectrumWorker | None = None
        self._closed = False

    def _check(self, settings: SpectrumSettings) -> None:
        if self._closed:
            raise RuntimeError("SpectrumRuntime is closed")
        if settings.backend != self.backend:
            raise ValueError("Request backend does not match runtime")

    def worker(self) -> SpectrumWorker:
        if self._closed:
            raise RuntimeError("SpectrumRuntime is closed")
        if self._worker is None:
            self._worker = SpectrumWorker(self.service, backend=self.backend)
        return self._worker

    def submit(self, request: SpectrumRequest) -> SpectrumJob:
        request.validate()
        self._check(request.settings)
        return self.worker().acquire(
            request.settings,
            owner=request.owner,
            dark_mode=request.dark_mode,
            dark=request.dark,
        )

    def close(self) -> None:
        if self._worker is not None:
            self._worker.close()
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _wrap(request: SpectrumRequest, result: SpectrumResult) -> SpectrumMeasurement:
    return SpectrumMeasurement(
        result,
        MeasurementProvenance(
            request.settings.backend,
            request.settings.configuration_id,
            request.settings.backend == "simulation",
        ),
    )


def acquire_spectrum(
    request: SpectrumRequest,
    *,
    runtime: SpectrumRuntime | None = None,
    timeout: float | None = None,
    progress: Progress | None = None,
) -> SpectrumMeasurement:
    request.validate()
    owned = runtime is None
    runtime = runtime or SpectrumRuntime(backend=request.settings.backend)
    try:
        if progress:
            progress("started")
        value = _wrap(request, runtime.submit(request).result(timeout))
        if progress:
            progress("completed")
        return value
    finally:
        if owned:
            runtime.close()


async def acquire_spectrum_async(
    request: SpectrumRequest,
    *,
    runtime: SpectrumRuntime | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    progress: Progress | None = None,
) -> SpectrumMeasurement:
    request.validate()
    owned = runtime is None
    runtime = runtime or SpectrumRuntime(backend=request.settings.backend)
    runtime._check(request.settings)
    try:
        if progress:
            progress("started")
        result = await runtime.service.acquire(
            request.settings,
            dark_mode=request.dark_mode,
            dark=request.dark,
            cancel_requested=cancel_requested or (lambda: False),
        )
        value = _wrap(request, result)
        if progress:
            progress("completed")
        return value
    finally:
        if owned:
            await asyncio.to_thread(runtime.close)
