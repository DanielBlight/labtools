"""Explicit backend composition for the opt-in spectrum service; no eager SDK imports."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import numpy as np

from labtools.acquisition.spectrum_service import RangeBackend, SpectrumService
from labtools.config.spectrum import SpectrumSettings


@asynccontextmanager
async def open_real_range(
    settings: SpectrumSettings,
    *,
    spectrometer_factory: Callable[..., Any] | None = None,
) -> AsyncIterator[RangeBackend]:
    settings.validate()
    if settings.backend != "real":
        raise ValueError("Real adapter refuses simulation settings")
    if spectrometer_factory is None:
        from labtools.devices.horiba_spectrometer import HoribaSpectrometer

        spectrometer_factory = HoribaSpectrometer
    from labtools.acquisition.range_spectrum import (
        capture_range_dark,
        get_range_spectrum,
    )

    spec = spectrometer_factory(preset=settings.preset)
    primary = None
    try:
        await spec.connect()
        await spec.configure(
            gain=settings.gain,
            speed=settings.speed,
            exposure_time=settings.exposure_s,
            roi=None,
            entrance_slit_width_mm=settings.slit_width_mm,
        )

        class Backend:
            async def capture_dark(self) -> tuple[np.ndarray, np.ndarray]:
                dark = await capture_range_dark(
                    spec,
                    settings.start_nm,
                    settings.end_nm,
                    stitch_pixel_overlap=settings.overlap_pixels,
                    n_frames=settings.n_frames,
                    mode=settings.combine_mode,
                )
                return dark.wavelength_nm, dark.intensity

            async def acquire(self, dark_mode: str) -> tuple[np.ndarray, np.ndarray]:
                return await get_range_spectrum(
                    spec,
                    settings.start_nm,
                    settings.end_nm,
                    stitch_pixel_overlap=settings.overlap_pixels,
                    n_frames=settings.n_frames,
                    mode=settings.combine_mode,
                    dark_mode=dark_mode,
                )

        yield Backend()
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            await spec.disconnect()
        except Exception as exc:
            if primary is None:
                raise
            primary.add_note(f"HORIBA disconnect also failed: {exc!r}")


def create_spectrum_service(*, backend: str) -> SpectrumService:
    """No implicit fallback, connection cache, singleton or cross-process lock."""
    if backend == "real":
        return SpectrumService(open_real_range)
    if backend == "simulation":
        from labtools.simulation.spectrum import open_simulated_range

        return SpectrumService(open_simulated_range)
    raise ValueError("backend must be real or simulation")
