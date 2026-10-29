"""Qt-free alignment-frame facade using the existing spectrum service boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from labtools.acquisition.alignment_spectrum import AlignmentResult, AlignmentSettings

from .spectrum import MeasurementProvenance, Progress, SpectrumRuntime


@dataclass(frozen=True)
class AlignmentRequest:
    settings: AlignmentSettings
    owner: str = "scripted-alignment"

    def validate(self) -> None:
        self.settings.validate()
        if not self.owner.strip():
            raise ValueError("owner must be nonempty")


@dataclass(frozen=True)
class AlignmentMeasurement:
    result: AlignmentResult
    provenance: MeasurementProvenance


def _wrap(request, result):
    s = request.settings
    return AlignmentMeasurement(
        result,
        MeasurementProvenance(s.backend, s.configuration_id, s.backend == "simulation"),
    )


def acquire_alignment_frame(
    request: AlignmentRequest,
    *,
    runtime: SpectrumRuntime | None = None,
    timeout: float | None = None,
    progress: Progress | None = None,
) -> AlignmentMeasurement:
    request.validate()
    owned = runtime is None
    runtime = runtime or SpectrumRuntime(backend=request.settings.backend)
    runtime._check(request.settings)
    try:
        if progress:
            progress("started")
        value = _wrap(
            request,
            runtime.worker()
            .acquire_alignment(request.settings, owner=request.owner)
            .result(timeout),
        )
        if progress:
            progress("completed")
        return value
    finally:
        if owned:
            runtime.close()


async def acquire_alignment_frame_async(
    request: AlignmentRequest,
    *,
    runtime: SpectrumRuntime | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    progress: Progress | None = None,
) -> AlignmentMeasurement:
    request.validate()
    owned = runtime is None
    runtime = runtime or SpectrumRuntime(backend=request.settings.backend)
    runtime._check(request.settings)
    try:
        if progress:
            progress("started")
        result = await runtime.service.acquire_alignment(
            request.settings, cancel_requested=cancel_requested or (lambda: False)
        )
        value = _wrap(request, result)
        if progress:
            progress("completed")
        return value
    finally:
        if owned:
            await asyncio.to_thread(runtime.close)
