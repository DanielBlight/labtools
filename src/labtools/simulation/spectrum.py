"""Deterministic toy range spectra, NOT a HORIBA SDK or physical shutter model."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import numpy as np

from labtools.acquisition.spectrum_service import RangeBackend
from labtools.config.spectrum import SpectrumSettings


@asynccontextmanager
async def open_simulated_range(
    settings: SpectrumSettings,
) -> AsyncIterator[RangeBackend]:
    settings.validate()
    if settings.backend != "simulation":
        raise ValueError("Synthetic adapter refuses real settings")
    x = np.linspace(settings.start_nm, settings.end_nm, 64)
    dark = np.full(x.shape, 10.0 + settings.exposure_s * 2.0)
    center = (settings.start_nm + settings.end_nm) / 2
    width = (settings.end_nm - settings.start_nm) / 10
    signal = settings.exposure_s * (
        100 + 1000 * np.exp(-0.5 * ((x - center) / width) ** 2)
    )
    closed = False

    class Backend:
        async def capture_dark(self) -> tuple[np.ndarray, np.ndarray]:
            if closed:
                raise RuntimeError("Synthetic spectrum backend is closed")
            return x.copy(), dark.copy()

        async def acquire(self, dark_mode: str) -> tuple[np.ndarray, np.ndarray]:
            if closed:
                raise RuntimeError("Synthetic spectrum backend is closed")
            if dark_mode not in {"none", "per_center", "per_frame"}:
                raise ValueError("Unsupported synthetic dark mode")
            # Identical deterministic frames have identical reductions in every
            # supported mode. No noise, timing, stitching or electronics model.
            return x.copy(), (signal + dark if dark_mode == "none" else signal).copy()

    try:
        yield Backend()
    finally:
        closed = True


@asynccontextmanager
async def open_simulated_alignment(settings):
    settings.validate()
    if settings.backend != "simulation":
        raise ValueError("Synthetic alignment adapter refuses real settings")

    class Backend:
        actual_centre_nm = float(settings.centre_nm)

        async def capture(self, subtract_dark):
            x = np.linspace(settings.centre_nm - 5.0, settings.centre_nm + 5.0, 64)
            raw = 100.0 + 900.0 * np.exp(-0.5 * ((x - settings.centre_nm) / 0.8) ** 2)
            dark = np.full_like(raw, 10.0)
            return x, raw - dark if subtract_dark else raw.copy(), raw

    yield Backend()
