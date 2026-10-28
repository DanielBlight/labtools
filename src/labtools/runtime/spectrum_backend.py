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
            # A cancelled job with failed cleanup must not advertise a healthy worker.
            primary._labtools_cleanup_failed = True


def create_spectrum_service(*, backend: str) -> SpectrumService:
    """No implicit fallback, connection cache, singleton or cross-process lock."""
    if backend == "real":
        return SpectrumService(open_real_range, open_real_alignment)
    if backend == "simulation":
        from labtools.simulation.spectrum import (
            open_simulated_alignment,
            open_simulated_range,
        )

        return SpectrumService(open_simulated_range, open_simulated_alignment)
    raise ValueError("backend must be real or simulation")


@asynccontextmanager
async def open_real_alignment(settings, *, spectrometer_factory=None):
    """One single-centre frame using the detector preset's normal exposure floor."""
    settings.validate()
    if settings.backend != "real":
        raise ValueError("Real alignment adapter refuses simulation settings")
    if spectrometer_factory is None:
        from labtools.devices.horiba_spectrometer import HoribaSpectrometer

        spectrometer_factory = HoribaSpectrometer
    spec = spectrometer_factory(preset=settings.preset)
    primary = None
    try:
        await spec.connect()
        await spec.configure(
            gain=settings.gain,
            speed=settings.speed,
            exposure_time=settings.exposure_s,
            roi=None,
        )
        actual = float(await spec.set_wavelength(settings.centre_nm))

        class Backend:
            actual_centre_nm = actual

            async def capture(self, subtract_dark):
                dark_x = dark_y = None
                if subtract_dark:
                    dark_x, dark_y = await spec.get_dark_spectrum(
                        n_frames=1, mode="single"
                    )
                    dark_x = np.asarray(dark_x, dtype=float)
                    dark_y = np.asarray(dark_y, dtype=float)
                x, raw = await spec.get_spectrum(
                    n_frames=1, mode="single", dark_frame_mode="none"
                )
                x = np.asarray(x, dtype=float)
                raw = np.asarray(raw, dtype=float)
                corrected = raw.copy()
                if subtract_dark:
                    if (
                        dark_x.shape != x.shape
                        or dark_y.shape != raw.shape
                        or not np.allclose(dark_x, x, rtol=0.0, atol=1e-8)
                    ):
                        raise RuntimeError("Dark wavelength axis does not match signal")
                    corrected -= dark_y
                order = np.argsort(x)
                return x[order], corrected[order], raw[order]

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
            # A cancelled job with failed cleanup must not advertise a healthy worker.
            primary._labtools_cleanup_failed = True
