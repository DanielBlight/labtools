"""Qt-free hyperspectral acquisition service.

This is an internal acquisition boundary, not a public ``labtools.measurements``
facade or recipe kind. Scan order intentionally matches the legacy runner:
y-major rows, with x increasing within each row.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import tempfile
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Self

import numpy as np

from labtools.acquisition.spectrum_service import (
    DarkRecord,
    SpectrumResult,
    SpectrumService,
)
from labtools.config.hyperspectral import (
    HYPERSPECTRAL_CONFIG_SCHEMA_VERSION,
    HyperspectralConfig,
)
from labtools.simulation.hyperspectral import SIMULATION_MODEL_ID

HYPERSPECTRAL_ARCHIVE_SCHEMA_VERSION = 1
HYPERSPECTRAL_SERVICE_VERSION = 1


class HyperspectralMirror(Protocol):
    backend_identity: str

    async def move_to(self, x_v: float, y_v: float) -> None: ...
    async def home(self) -> None: ...


@dataclass(frozen=True)
class HyperspectralProgress:
    phase: str
    completed_points: int
    total_points: int
    y_index: int | None = None
    x_index: int | None = None


@dataclass(frozen=True)
class HyperspectralProvenance:
    configuration_id: str
    configuration_identity: str
    requested_backend: str
    mirror_backend_identity: str
    spectrum_backend: str
    synthetic: bool
    simulation_model_id: str | None
    service_version: int
    archive_schema_version: int
    config_schema_version: int
    scan_order: str
    created_utc: str


@dataclass(frozen=True)
class HyperspectralResult:
    status: str
    x_v: np.ndarray
    y_v: np.ndarray
    wavelength_nm: np.ndarray
    intensity: np.ndarray
    completed_mask: np.ndarray
    completed_points: int
    output_path: Path | None
    provenance: HyperspectralProvenance
    failure_type: str | None = None
    failure_message: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"complete", "cancelled", "failed"}:
            raise ValueError("Unknown hyperspectral result status")
        for value in (
            self.x_v,
            self.y_v,
            self.wavelength_nm,
            self.intensity,
            self.completed_mask,
        ):
            value.setflags(write=False)


class HyperspectralAcquisitionError(RuntimeError):
    """Acquisition failed after producing an immutable diagnostic result."""

    def __init__(self, message: str, *, partial_result: HyperspectralResult) -> None:
        super().__init__(message)
        self.partial_result = partial_result


ProgressCallback = Callable[[HyperspectralProgress], None]
CancelCallback = Callable[[], bool]
MirrorFactory = Callable[[], AbstractAsyncContextManager[HyperspectralMirror]]


def _atomic_savez(path: Path, **arrays: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        with temporary_path.open("wb") as stream:
            np.savez(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def save_hyperspectral_result(
    result: HyperspectralResult, path: Path, *, overwrite: bool = False
) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    metadata = {
        "status": result.status,
        "completed_points": result.completed_points,
        "failure_type": result.failure_type,
        "failure_message": result.failure_message,
        "provenance": asdict(result.provenance),
    }
    _atomic_savez(
        path,
        metadata_json=np.array(json.dumps(metadata, sort_keys=True)),
        x_v=result.x_v,
        y_v=result.y_v,
        wavelength_nm=result.wavelength_nm,
        intensity=result.intensity,
        completed_mask=result.completed_mask,
    )


def load_hyperspectral_result(path: Path) -> HyperspectralResult:
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
        provenance = HyperspectralProvenance(**metadata["provenance"])
        if provenance.archive_schema_version != HYPERSPECTRAL_ARCHIVE_SCHEMA_VERSION:
            raise ValueError("Unsupported hyperspectral archive schema")
        return HyperspectralResult(
            status=metadata["status"],
            x_v=np.array(archive["x_v"], copy=True),
            y_v=np.array(archive["y_v"], copy=True),
            wavelength_nm=np.array(archive["wavelength_nm"], copy=True),
            intensity=np.array(archive["intensity"], copy=True),
            completed_mask=np.array(archive["completed_mask"], dtype=bool, copy=True),
            completed_points=int(metadata["completed_points"]),
            output_path=path,
            provenance=provenance,
            failure_type=metadata.get("failure_type"),
            failure_message=metadata.get("failure_message"),
        )


class HyperspectralService:
    """Acquire a spectral cube with explicit borrowed/owned dependencies."""

    def __init__(
        self,
        spectrum_service: SpectrumService,
        mirror_factory: MirrorFactory,
        *,
        owns_spectrum_service: bool = False,
    ) -> None:
        self._spectra = spectrum_service
        self._mirror_factory = mirror_factory
        self._owns_spectra = owns_spectrum_service
        self._closed = False

    async def __aenter__(self) -> Self:
        if self._closed:
            raise RuntimeError("HyperspectralService is closed")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close(primary=exc)

    async def close(self, *, primary: BaseException | None = None) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._owns_spectra:
            return
        close = getattr(self._spectra, "close", None)
        if close is None:
            return
        try:
            outcome = close()
            if hasattr(outcome, "__await__"):
                await outcome
        except BaseException as cleanup_error:
            if isinstance(cleanup_error, (KeyboardInterrupt, SystemExit)):
                raise
            if primary is not None:
                primary.add_note(
                    f"Hyperspectral spectrum-service cleanup failed: {cleanup_error!r}"
                )
            else:
                raise

    async def acquire(
        self,
        config: HyperspectralConfig,
        *,
        dark: DarkRecord | None = None,
        output_path: Path | None = None,
        progress: ProgressCallback | None = None,
        cancel_requested: CancelCallback | None = None,
    ) -> HyperspectralResult:
        if self._closed:
            raise RuntimeError("HyperspectralService is closed")
        config.validate()
        if config.dark_mode == "pre_taken" and dark is None:
            raise ValueError("pre_taken dark mode requires a DarkRecord")
        if output_path is not None and output_path.exists():
            raise FileExistsError(output_path)
        x_v = np.linspace(config.x_start_v, config.x_stop_v, config.x_points)
        y_v = np.linspace(config.y_start_v, config.y_stop_v, config.y_points)
        completed = np.zeros((config.y_points, config.x_points), dtype=bool)
        wavelength = np.empty(0, dtype=float)
        cube = np.empty((config.y_points, config.x_points, 0), dtype=float)
        total = config.x_points * config.y_points
        mirror_identity = "unknown"
        status = "failed"
        failure: Exception | None = None

        def emit(
            phase: str, done: int, iy: int | None = None, ix: int | None = None
        ) -> None:
            if progress is not None:
                progress(HyperspectralProgress(phase, done, total, iy, ix))

        def provenance() -> HyperspectralProvenance:
            synthetic = config.backend == "simulation"
            return HyperspectralProvenance(
                configuration_id=config.configuration_id,
                configuration_identity=config.identity(),
                requested_backend=config.backend,
                mirror_backend_identity=mirror_identity,
                spectrum_backend=config.spectrum.backend,
                synthetic=synthetic,
                simulation_model_id=SIMULATION_MODEL_ID if synthetic else None,
                service_version=HYPERSPECTRAL_SERVICE_VERSION,
                archive_schema_version=HYPERSPECTRAL_ARCHIVE_SCHEMA_VERSION,
                config_schema_version=HYPERSPECTRAL_CONFIG_SCHEMA_VERSION,
                scan_order="y-major/x-minor",
                created_utc=datetime.now(UTC).isoformat(),
            )

        def result(
            state: str, problem: BaseException | None = None
        ) -> HyperspectralResult:
            return HyperspectralResult(
                state,
                x_v.copy(),
                y_v.copy(),
                wavelength.copy(),
                cube.copy(),
                completed.copy(),
                int(completed.sum()),
                output_path,
                provenance(),
                type(problem).__name__ if problem else None,
                str(problem) if problem else None,
            )

        emit("starting", 0)
        try:
            async with self._mirror_factory() as mirror:
                mirror_identity = mirror.backend_identity
                expected_prefix = (
                    "simulation:" if config.backend == "simulation" else "real:"
                )
                if not mirror_identity.startswith(expected_prefix):
                    raise ValueError(
                        "Mirror backend identity does not match requested backend"
                    )
                for iy, y in enumerate(y_v):
                    for ix, x in enumerate(x_v):
                        if cancel_requested is not None and cancel_requested():
                            status = "cancelled"
                            emit("cancelled", int(completed.sum()), iy, ix)
                            partial = result(status)
                            if output_path is not None:
                                save_hyperspectral_result(partial, output_path)
                            return partial
                        emit("point_started", int(completed.sum()), iy, ix)
                        await mirror.move_to(float(x), float(y))
                        if config.settle_time_s:
                            await asyncio.sleep(config.settle_time_s)
                        spectrum: SpectrumResult = await self._spectra.acquire(
                            config.spectrum,
                            dark_mode=config.dark_mode,
                            dark=dark,
                            cancel_requested=cancel_requested,
                        )
                        values = np.asarray(spectrum.intensity, dtype=float)
                        axis = np.asarray(spectrum.wavelength_nm, dtype=float)
                        if wavelength.size == 0:
                            wavelength = axis.copy()
                            cube = np.full(
                                (config.y_points, config.x_points, axis.size), np.nan
                            )
                        elif not np.array_equal(axis, wavelength):
                            raise ValueError(
                                "Spectrum wavelength axis changed during hyperspectral scan"
                            )
                        if config.backend == "simulation":
                            x_span = max(abs(config.x_stop_v - config.x_start_v), 1.0)
                            y_span = max(abs(config.y_stop_v - config.y_start_v), 1.0)
                            modulation = 1.0 + 0.25 * math.exp(
                                -4.0
                                * (
                                    ((x - x_v.mean()) / x_span) ** 2
                                    + ((y - y_v.mean()) / y_span) ** 2
                                )
                            )
                            values = values * modulation
                        cube[iy, ix] = values
                        completed[iy, ix] = True
                        emit("point_completed", int(completed.sum()), iy, ix)
                status = "complete"
        except asyncio.CancelledError:
            status = "cancelled"
        except (KeyboardInterrupt, SystemExit):
            raise
        # Preserve an arbitrary acquisition failure while recording and
        # persisting its immutable partial result before re-raising it.
        except Exception as error:  # noqa: BLE001
            failure = error
            status = "failed"
        final = result(status, failure)
        if output_path is not None:
            try:
                save_hyperspectral_result(final, output_path)
            except BaseException as persistence_error:
                if isinstance(persistence_error, (KeyboardInterrupt, SystemExit)):
                    raise
                if failure is not None:
                    failure.add_note(
                        f"Hyperspectral persistence failed: {persistence_error!r}"
                    )
                else:
                    raise
        emit(status, final.completed_points)
        if failure is not None:
            error = HyperspectralAcquisitionError(
                "Hyperspectral acquisition failed", partial_result=final
            )
            for note in getattr(failure, "__notes__", ()):
                error.add_note(note)
            raise error from failure
        return final
