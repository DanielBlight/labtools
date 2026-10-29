"""Public Qt-free hyperspectral measurement facade."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from labtools.acquisition.hyperspectral import (
    HyperspectralProgress,
    HyperspectralResult,
    load_hyperspectral_result,
)
from labtools.acquisition.spectrum_service import DarkRecord
from labtools.config.hyperspectral import HyperspectralConfig
from labtools.runtime.hyperspectral import (
    HyperspectralMirrorProvider,
    open_hyperspectral_service,
)
from labtools.runtime.spectrum_backend import create_spectrum_service
from labtools.simulation.hyperspectral import open_simulated_hyperspectral_mirror

Progress = Callable[[HyperspectralProgress], None]
Cancel = Callable[[], bool]


@dataclass(frozen=True)
class HyperspectralRequest:
    config: HyperspectralConfig
    output_path: Path | None = None
    dark: DarkRecord | None = None
    owner: str = "scripted-hyperspectral"

    def validate(self) -> None:
        self.config.validate()
        if not self.owner.strip():
            raise ValueError("owner must be nonempty")
        if self.output_path is not None:
            if not isinstance(self.output_path, Path):
                raise ValueError("output_path must be a pathlib.Path")
            if self.output_path.exists():
                raise FileExistsError(self.output_path)
        if self.config.dark_mode == "pre_taken":
            if self.dark is None:
                raise ValueError("pre_taken requires a DarkRecord")
            self.dark.validate_for(self.config.spectrum)
        elif self.dark is not None:
            raise ValueError("DarkRecord is only valid for pre_taken mode")


@dataclass(frozen=True)
class HyperspectralMeasurementProvenance:
    backend: str
    configuration_id: str
    configuration_identity: str
    mirror_backend_identity: str
    spectrum_backend: str
    synthetic: bool
    simulation_model_id: str | None
    service_version: int
    config_schema_version: int
    archive_schema_version: int
    scan_order: str


@dataclass(frozen=True)
class HyperspectralMeasurement:
    result: HyperspectralResult
    provenance: HyperspectralMeasurementProvenance


class HyperspectralRuntime:
    """Explicit owner/borrower composition for one public acquisition."""

    def __init__(
        self,
        *,
        backend: str,
        spectrum_service=None,
        mirror_factory=None,
        session=None,
        owns_spectrum_service: bool | None = None,
        owns_session: bool = False,
    ) -> None:
        if backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        if mirror_factory is not None and session is not None:
            raise ValueError("Choose mirror_factory or session")
        self.backend = backend
        self.spectrum_service = spectrum_service or create_spectrum_service(
            backend=backend
        )
        self._owns_spectrum = (
            spectrum_service is None
            if owns_spectrum_service is None
            else owns_spectrum_service
        )
        self.session = session
        self._owns_session = owns_session
        if mirror_factory is None:
            if backend == "simulation":
                mirror_factory = open_simulated_hyperspectral_mirror
            elif session is not None:
                mirror_factory = HyperspectralMirrorProvider(session)
        self.mirror_factory = mirror_factory
        self._closed = False

    def check(self, config: HyperspectralConfig) -> None:
        if self._closed:
            raise RuntimeError("HyperspectralRuntime is closed")
        if config.backend != self.backend:
            raise ValueError("Request backend does not match runtime")
        if self.mirror_factory is None:
            raise RuntimeError(
                "Real hyperspectral runtime requires an InstrumentSession"
            )

    def close(self) -> None:
        if self._closed:
            return
        failures = []
        for value, owned in (
            (self.spectrum_service, self._owns_spectrum),
            (self.session, self._owns_session),
        ):
            if value is not None and owned and callable(getattr(value, "close", None)):
                try:
                    value.close()
                except BaseException as exc:  # noqa: BLE001 - attempt all owned cleanup
                    failures.append(exc)
        self._closed = True
        if failures:
            primary = next((e for e in failures if not isinstance(e, Exception)), None)
            if primary is not None:
                for failure in failures:
                    if failure is not primary:
                        primary.add_note(
                            f"Additional hyperspectral cleanup failed: {failure!r}"
                        )
                raise primary
            raise ExceptionGroup("Hyperspectral runtime cleanup failed", failures)


def _wrap(result: HyperspectralResult) -> HyperspectralMeasurement:
    p = result.provenance
    return HyperspectralMeasurement(
        result,
        HyperspectralMeasurementProvenance(
            p.requested_backend,
            p.configuration_id,
            p.configuration_identity,
            p.mirror_backend_identity,
            p.spectrum_backend,
            p.synthetic,
            p.simulation_model_id,
            p.service_version,
            p.config_schema_version,
            p.archive_schema_version,
            p.scan_order,
        ),
    )


async def acquire_hyperspectral_map_async(
    request: HyperspectralRequest,
    *,
    runtime: HyperspectralRuntime | None = None,
    progress: Progress | None = None,
    cancel_requested: Cancel | None = None,
) -> HyperspectralMeasurement:
    request.validate()
    owned = runtime is None
    runtime = runtime or HyperspectralRuntime(backend=request.config.backend)
    runtime.check(request.config)
    try:
        async with open_hyperspectral_service(
            request.config,
            spectrum_service=runtime.spectrum_service,
            mirror_factory=runtime.mirror_factory,
            cancel_requested=cancel_requested,
        ) as service:
            result = await service.acquire(
                request.config,
                dark=request.dark,
                output_path=request.output_path,
                progress=progress,
                cancel_requested=cancel_requested,
            )
        return _wrap(result)
    finally:
        if owned:
            runtime.close()


def acquire_hyperspectral_map(
    request: HyperspectralRequest,
    *,
    runtime: HyperspectralRuntime | None = None,
    progress: Progress | None = None,
    cancel_requested: Cancel | None = None,
) -> HyperspectralMeasurement:
    return asyncio.run(
        acquire_hyperspectral_map_async(
            request,
            runtime=runtime,
            progress=progress,
            cancel_requested=cancel_requested,
        )
    )


__all__ = [
    "HyperspectralMeasurement",
    "HyperspectralMeasurementProvenance",
    "HyperspectralRequest",
    "HyperspectralRuntime",
    "acquire_hyperspectral_map",
    "acquire_hyperspectral_map_async",
    "load_hyperspectral_result",
]
