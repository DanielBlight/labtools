"""Qt-free facade over the existing resumable intensity-map acquisition."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labtools.acquisition.intensity_map import (
    IntensityMapResult,
    IntensityMapSnapshot,
    config_from_resume_directory,
)
from labtools.acquisition.intensity_map import acquire_intensity_map as _acquire
from labtools.config.intensity_map import SCHEMA_VERSION, IntensityMapConfig


@dataclass(frozen=True)
class IntensityMapRequest:
    config: IntensityMapConfig
    resume_directory: Path | None = None
    owner: str = "scripted-intensity-map"

    def validate(self) -> None:
        self.config.validate()
        if not self.owner.strip():
            raise ValueError("owner must be nonempty")


@dataclass(frozen=True)
class IntensityMapProvenance:
    backend: str
    schema_version: int
    synthetic: bool
    checkpoint_signature: dict[str, Any]


@dataclass(frozen=True)
class IntensityMapMeasurement:
    result: IntensityMapResult
    provenance: IntensityMapProvenance


class IntensityMapRuntime:
    """Explicit owner or borrower of map device-provider composition."""

    def __init__(self, *, backend: str, application=None, device_provider=None) -> None:
        if backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        if application is not None and device_provider is not None:
            raise ValueError("Choose application or device_provider")
        self.backend = backend
        self.application = application
        self.device_provider = device_provider
        self._closed = False

    def check(self, config):
        if self._closed:
            raise RuntimeError("IntensityMapRuntime is closed")
        if config.backend != self.backend:
            raise ValueError("Request backend does not match runtime")

    def provider(self):
        if self.application is not None:
            return self.application.map_provider
        return self.device_provider

    def close(self):
        if self.application is not None:
            self.application.close()
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _wrap(request, result):
    c = request.config
    return IntensityMapMeasurement(
        result,
        IntensityMapProvenance(
            c.backend,
            SCHEMA_VERSION,
            c.backend == "simulation",
            c.checkpoint_signature(),
        ),
    )


def acquire_intensity_map(
    request: IntensityMapRequest,
    *,
    runtime: IntensityMapRuntime | None = None,
    progress: Callable[[IntensityMapSnapshot], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> IntensityMapMeasurement:
    request.validate()
    owned = runtime is None
    runtime = runtime or IntensityMapRuntime(backend=request.config.backend)
    runtime.check(request.config)
    try:
        result = _acquire(
            request.config,
            resume_directory=request.resume_directory,
            progress_callback=progress,
            cancel_requested=cancel_requested,
            device_provider=runtime.provider(),
        )
        return _wrap(request, result)
    finally:
        if owned:
            runtime.close()


async def acquire_intensity_map_async(
    request: IntensityMapRequest,
    *,
    runtime: IntensityMapRuntime | None = None,
    progress=None,
    cancel_requested=None,
) -> IntensityMapMeasurement:
    return await asyncio.to_thread(
        acquire_intensity_map,
        request,
        runtime=runtime,
        progress=progress,
        cancel_requested=cancel_requested,
    )


def request_from_resume(
    path: str | Path, *, owner: str = "scripted-intensity-map"
) -> IntensityMapRequest:
    directory = Path(path).expanduser().resolve()
    return IntensityMapRequest(
        config_from_resume_directory(directory), directory, owner
    )
