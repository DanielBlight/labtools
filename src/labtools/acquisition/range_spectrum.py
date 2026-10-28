"""Stitched HORIBA range-spectrum acquisition and reusable dark spectra."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np
from loguru import logger

from labtools.processing.dark_spectrum import DarkSpectrum, subtract_dark_spectrum
from labtools.processing.spectrum import CombineMode

if TYPE_CHECKING:
    from labtools.devices.horiba_spectrometer import HoribaSpectrometer

RangeDarkMode = Literal["none", "per_center", "per_frame", "pre_taken"]


def _vendor_capture(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
) -> list:
    """Convert matching 1D arrays to the structure expected by the stitcher."""
    x_data = np.asarray(wavelength_nm, dtype=float)
    y_data = np.asarray(intensity, dtype=float)

    if x_data.ndim != 1 or y_data.ndim != 1 or x_data.shape != y_data.shape:
        raise RuntimeError(
            "A stitched capture requires matching one-dimensional arrays; "
            f"received x={x_data.shape}, y={y_data.shape}."
        )

    return [x_data.tolist(), [y_data.tolist()]]


def _stitch_and_filter(
    captures: list[list],
    start_wavelength: float,
    end_wavelength: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Stitch vendor-format captures and trim the requested range."""
    if not captures:
        raise RuntimeError("No spectra were captured for stitching.")

    from horiba_sdk.core.stitching import LinearSpectraStitch

    stitched = LinearSpectraStitch(captures).stitched_spectra()
    x_data = np.asarray(stitched[0], dtype=float)
    y_data = np.asarray(stitched[1][0], dtype=float)

    if x_data.ndim != 1 or y_data.ndim != 1 or x_data.shape != y_data.shape:
        raise RuntimeError(
            "Stitched wavelength and intensity arrays are inconsistent: "
            f"x={x_data.shape}, y={y_data.shape}."
        )

    mask = (x_data >= start_wavelength) & (x_data <= end_wavelength)
    if not np.any(mask):
        raise RuntimeError("The stitched spectrum does not cover the requested range.")

    return x_data[mask], y_data[mask]


async def _center_wavelengths(
    spec: HoribaSpectrometer,
    start_wavelength: float,
    end_wavelength: float,
    stitch_pixel_overlap: int,
) -> list[float]:
    """Calculate the centre wavelengths required for a range scan."""
    if stitch_pixel_overlap < 0:
        raise ValueError("stitch_pixel_overlap cannot be negative.")
    if start_wavelength == end_wavelength:
        raise ValueError("Start and end wavelengths must be different.")

    current_wavelength = await spec.prepare_wavelength_axis()
    logger.debug(
        "Calculating range centres from {:.3f} to {:.3f} nm with "
        "{}-pixel overlap; current wavelength is {:.3f} nm",
        start_wavelength,
        end_wavelength,
        stitch_pixel_overlap,
        current_wavelength,
    )

    values = await spec.ccd.range_mode_center_wavelengths(
        spec.mono.id(),
        float(start_wavelength),
        float(end_wavelength),
        int(stitch_pixel_overlap),
    )
    centers = [float(value) for value in values]

    if not centers:
        raise RuntimeError("HORIBA range mode returned no centre wavelengths.")
    if not all(np.isfinite(center) for center in centers):
        raise RuntimeError("HORIBA range mode returned a non-finite centre wavelength.")

    logger.info(
        "HORIBA range calculation returned {} centre wavelength(s)", len(centers)
    )
    return centers


async def capture_range_dark(
    spec: HoribaSpectrometer,
    start_wavelength: float,
    end_wavelength: float,
    *,
    stitch_pixel_overlap: int = 20,
    n_frames: int = 1,
    mode: CombineMode = "single",
) -> DarkSpectrum:
    """Capture one reusable stitched dark spectrum across the full range."""
    if end_wavelength < start_wavelength:
        start_wavelength, end_wavelength = end_wavelength, start_wavelength

    centers = await _center_wavelengths(
        spec,
        start_wavelength,
        end_wavelength,
        stitch_pixel_overlap,
    )

    captures: list[list] = []
    for index, center in enumerate(centers, start=1):
        actual = await spec.set_wavelength(center)
        logger.info(
            "Capturing dark at centre {}/{}: {:.3f} nm",
            index,
            len(centers),
            actual,
        )
        x_data, y_data = await spec.get_dark_spectrum(
            n_frames=n_frames,
            mode=mode,
        )
        captures.append(_vendor_capture(x_data, y_data))

    x_out, y_out = _stitch_and_filter(
        captures,
        start_wavelength,
        end_wavelength,
    )
    return DarkSpectrum(x_out, y_out)


async def get_range_spectrum(
    spec: HoribaSpectrometer,
    start_wavelength: float,
    end_wavelength: float,
    *,
    stitch_pixel_overlap: int = 20,
    n_frames: int = 1,
    mode: CombineMode = "single",
    dark_mode: RangeDarkMode = "none",
    pre_taken_dark: DarkSpectrum | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Acquire a stitched spectrum with selectable dark-frame behaviour."""
    if dark_mode not in {"none", "per_center", "per_frame", "pre_taken"}:
        raise ValueError(f"Unsupported dark_mode {dark_mode!r}.")
    if dark_mode == "pre_taken" and pre_taken_dark is None:
        raise ValueError("pre_taken_dark is required for dark_mode='pre_taken'.")
    if dark_mode != "pre_taken" and pre_taken_dark is not None:
        raise ValueError("pre_taken_dark may only be used with dark_mode='pre_taken'.")
    if end_wavelength < start_wavelength:
        start_wavelength, end_wavelength = end_wavelength, start_wavelength

    centers = await _center_wavelengths(
        spec,
        start_wavelength,
        end_wavelength,
        stitch_pixel_overlap,
    )
    logger.info("Range scan requires {} centre wavelength(s)", len(centers))

    frame_dark_mode = {
        "none": "none",
        "per_center": "once",
        "per_frame": "per_frame",
        "pre_taken": "none",
    }[dark_mode]

    captures: list[list] = []
    for index, center in enumerate(centers, start=1):
        actual = await spec.set_wavelength(center)
        logger.info(
            "Capturing centre {}/{}: {:.3f} nm",
            index,
            len(centers),
            actual,
        )
        x_data, y_data = await spec.get_spectrum(
            n_frames=n_frames,
            mode=mode,
            dark_frame_mode=frame_dark_mode,
        )
        captures.append(_vendor_capture(x_data, y_data))

    x_out, y_out = _stitch_and_filter(
        captures,
        start_wavelength,
        end_wavelength,
    )

    if dark_mode == "pre_taken":
        if pre_taken_dark is None:
            raise RuntimeError("Internal error: pre-taken dark is missing.")
        y_out = subtract_dark_spectrum(x_out, y_out, pre_taken_dark)

    return x_out, y_out
