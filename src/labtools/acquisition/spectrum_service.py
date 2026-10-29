"""Opt-in reusable range-spectrum orchestration, independent of Qt/native SDKs.

The ordinary spectrum GUI uses this service. Each operation owns one backend context;
real connect/use/disconnect therefore stay on the caller's one asyncio loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import numpy as np
from numpy.typing import ArrayLike

from labtools.config.spectrum import SpectrumSettings
from labtools.processing.dark_spectrum import DarkSpectrum, subtract_dark_spectrum


def owned_vector(values: ArrayLike) -> np.ndarray:
    """Finite nonempty 1D data, copied into an immutable bytes-backed buffer."""
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or not array.size or not np.isfinite(array).all():
        raise ValueError("Spectrum arrays must be finite, nonempty and one-dimensional")
    return np.frombuffer(array.tobytes(), dtype=float)


@dataclass(frozen=True)
class DarkRecord:
    settings: SpectrumSettings
    wavelength_nm: np.ndarray
    intensity: np.ndarray
    record_id: str
    captured_at: str

    def __post_init__(self) -> None:
        self.settings.validate()
        if not isinstance(self.record_id, str) or not self.record_id.strip():
            raise ValueError("Dark record requires an identifier")
        stamp = datetime.fromisoformat(self.captured_at)
        if stamp.tzinfo is None:
            raise ValueError("Dark timestamp must include a timezone")
        x, y = owned_vector(self.wavelength_nm), owned_vector(self.intensity)
        if x.shape != y.shape:
            raise ValueError("Dark array shapes differ")
        object.__setattr__(self, "wavelength_nm", x)
        object.__setattr__(self, "intensity", y)

    def validate_for(self, settings: SpectrumSettings) -> None:
        settings.validate()
        if self.settings != settings:
            raise ValueError(
                "Stored dark settings differ; recapture the dark. No exposure scaling is performed."
            )


@dataclass(frozen=True)
class SpectrumResult:
    settings: SpectrumSettings
    wavelength_nm: np.ndarray
    intensity: np.ndarray
    raw_intensity: np.ndarray | None
    dark_mode: str
    dark_record_id: str | None

    def __post_init__(self) -> None:
        self.settings.validate()
        if self.dark_mode not in {"none", "per_center", "per_frame", "pre_taken"}:
            raise ValueError("Unknown result dark mode")
        if self.dark_mode == "pre_taken":
            if (
                not isinstance(self.dark_record_id, str)
                or not self.dark_record_id.strip()
            ):
                raise ValueError("Corrected result requires a dark record identifier")
        elif self.dark_record_id is not None:
            raise ValueError("Dark record identifier is only valid for pre_taken mode")
        x, y = owned_vector(self.wavelength_nm), owned_vector(self.intensity)
        raw = None if self.raw_intensity is None else owned_vector(self.raw_intensity)
        if x.shape != y.shape or (raw is not None and raw.shape != x.shape):
            raise ValueError("Spectrum result shapes differ")
        object.__setattr__(self, "wavelength_nm", x)
        object.__setattr__(self, "intensity", y)
        object.__setattr__(self, "raw_intensity", raw)


class RangeBackend(Protocol):
    """Already configured backend. Context factory owns connection/cleanup."""

    async def capture_dark(self) -> tuple[np.ndarray, np.ndarray]: ...
    async def acquire(self, dark_mode: str) -> tuple[np.ndarray, np.ndarray]: ...


BackendFactory = Callable[[SpectrumSettings], AbstractAsyncContextManager[RangeBackend]]


class AlignmentBackend(Protocol):
    actual_centre_nm: float

    async def capture(
        self, subtract_dark: bool
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...


AlignmentBackendFactory = Callable[
    [object], AbstractAsyncContextManager[AlignmentBackend]
]


class SpectrumService:
    """One acquisition path for real/synthetic range backends.

    Cancellation is cooperative before opening and after a complete backend
    operation. It does not abort a native call or add per-frame cancellation.
    Context cleanup completes before a cancellation/error escapes.
    """

    def __init__(
        self,
        backend_factory: BackendFactory,
        alignment_backend_factory: AlignmentBackendFactory | None = None,
    ) -> None:
        self._backend_factory = backend_factory
        self._alignment_backend_factory = alignment_backend_factory

    @asynccontextmanager
    async def operation(
        self,
        settings: SpectrumSettings,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ):
        """Borrow one configured range backend for a multi-acquisition operation.

        The returned service preserves normal validation, dark handling and
        result construction while the outer context owns backend teardown.
        """
        settings.validate()
        self._cancel(cancel_requested)
        async with self._backend_factory(settings) as backend:

            @asynccontextmanager
            async def borrowed(request: SpectrumSettings):
                if request != settings:
                    raise ValueError("Operation spectrum settings must match exactly")
                yield backend

            yield SpectrumService(borrowed)
        self._cancel(cancel_requested)

    @staticmethod
    def _cancel(cancel_requested: Callable[[], bool] | None) -> None:
        if cancel_requested is not None and cancel_requested():
            raise asyncio.CancelledError("Spectrum operation cancelled")

    async def acquire_alignment(
        self,
        settings,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ):
        """Acquire one immutable alignment frame through the service boundary."""
        from labtools.acquisition.alignment_spectrum import AlignmentResult

        settings.validate()
        if self._alignment_backend_factory is None:
            raise RuntimeError("Alignment is unavailable for this service")
        self._cancel(cancel_requested)
        async with self._alignment_backend_factory(settings) as backend:
            wavelength, corrected, raw = await backend.capture(settings.subtract_dark)
            self._cancel(cancel_requested)
            return AlignmentResult(
                settings,
                wavelength,
                corrected,
                raw,
                backend.actual_centre_nm,
                settings.subtract_dark,
            )

    async def test_connection(
        self,
        settings: SpectrumSettings,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> None:
        """Open/configure/close the backend, with cleanup before cancellation escapes."""
        settings.validate()
        self._cancel(cancel_requested)
        async with self._backend_factory(settings):
            self._cancel(cancel_requested)

    async def capture_dark(
        self,
        settings: SpectrumSettings,
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> DarkRecord:
        settings.validate()
        self._cancel(cancel_requested)
        async with self._backend_factory(settings) as backend:
            x, y = await backend.capture_dark()
            self._cancel(cancel_requested)
            return DarkRecord(
                settings, x, y, uuid4().hex, datetime.now(UTC).isoformat()
            )

    async def acquire(
        self,
        settings: SpectrumSettings,
        *,
        dark_mode: str = "none",
        dark: DarkRecord | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> SpectrumResult:
        settings.validate()
        if dark_mode not in {"none", "per_center", "per_frame", "pre_taken"}:
            raise ValueError("Unknown dark mode")
        if dark_mode == "pre_taken":
            if dark is None:
                raise ValueError(
                    "A provenance-bearing DarkRecord is required; legacy CSV is unverified"
                )
            dark.validate_for(settings)
        elif dark is not None:
            raise ValueError("Supply a dark only for pre_taken mode")
        self._cancel(cancel_requested)
        async with self._backend_factory(settings) as backend:
            x, y = await backend.acquire(
                "none" if dark_mode == "pre_taken" else dark_mode
            )
            self._cancel(cancel_requested)
            # Validate/copy before subtraction; never mutate caller/backend arrays.
            raw = SpectrumResult(settings, x, y, y, "none", None)
            if dark_mode == "pre_taken":
                corrected = subtract_dark_spectrum(
                    raw.wavelength_nm,
                    raw.intensity,
                    DarkSpectrum(dark.wavelength_nm, dark.intensity),
                )
                return SpectrumResult(
                    settings,
                    raw.wavelength_nm,
                    corrected,
                    raw.intensity,
                    dark_mode,
                    dark.record_id,
                )
            # Legacy fresh-dark paths combine corrected frames internally. Raw
            # cannot be reconstructed for nonlinear reductions; do not invent it.
            return SpectrumResult(
                settings,
                raw.wavelength_nm,
                raw.intensity,
                raw.intensity if dark_mode == "none" else None,
                dark_mode,
                None,
            )
