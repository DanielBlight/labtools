"""Stitched HORIBA range-spectrum acquisition and reusable dark spectra."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from horiba_sdk.core.stitching import LinearSpectraStitch
from loguru import logger

from labtools.devices.horiba_spectrometer import CombineMode, HoribaSpectrometer

RangeDarkMode = Literal["none", "per_center", "per_frame", "pre_taken"]


@dataclass(frozen=True)
class DarkSpectrum:
    """Reusable stitched dark spectrum on a wavelength axis."""

    wavelength_nm: np.ndarray
    intensity: np.ndarray

    def __post_init__(self) -> None:
        x = np.asarray(self.wavelength_nm, dtype=float)
        y = np.asarray(self.intensity, dtype=float)
        if x.ndim != 1 or y.ndim != 1 or x.shape != y.shape:
            raise ValueError("DarkSpectrum arrays must be matching 1D arrays.")
        if x.size == 0:
            raise ValueError("DarkSpectrum cannot be empty.")
        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            raise ValueError("DarkSpectrum values must be finite.")
        object.__setattr__(self, "wavelength_nm", x)
        object.__setattr__(self, "intensity", y)

    def save_csv(self, path: str | Path) -> None:
        """Save wavelength and dark intensity as a two-column CSV."""
        data = np.column_stack((self.wavelength_nm, self.intensity))
        np.savetxt(
            path,
            data,
            delimiter=",",
            header="wavelength_nm,intensity",
            comments="",
        )

    @classmethod
    def load_csv(cls, path: str | Path) -> DarkSpectrum:
        """Load a two-column wavelength/intensity dark CSV."""
        data = np.genfromtxt(path, delimiter=",", names=True)
        if data.dtype.names and len(data.dtype.names) >= 2:
            x = np.asarray(data[data.dtype.names[0]], dtype=float)
            y = np.asarray(data[data.dtype.names[1]], dtype=float)
        else:
            plain = np.loadtxt(path, delimiter=",", ndmin=2)
            if plain.shape[1] < 2:
                raise ValueError("Dark CSV must contain at least two columns.")
            x, y = plain[:, 0], plain[:, 1]
        return cls(x, y)


def subtract_dark_spectrum(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    dark: DarkSpectrum,
    *,
    wavelength_tolerance_nm: float = 1e-8,
) -> np.ndarray:
    """Subtract a reusable dark after validating its wavelength axis."""
    x = np.asarray(wavelength_nm, dtype=float)
    y = np.asarray(intensity, dtype=float)
    if x.shape != y.shape:
        raise ValueError("Signal wavelength and intensity shapes differ.")
    if dark.wavelength_nm.shape != x.shape or not np.allclose(
        dark.wavelength_nm,
        x,
        rtol=0.0,
        atol=wavelength_tolerance_nm,
    ):
        raise ValueError(
            "Pre-taken dark wavelength values do not match this range spectrum. "
            "Use the same range, overlap, detector, ROI, grating, and calibration."
        )
    return y - dark.intensity


def _stitch_and_filter(
    captures: list[list],
    start_wavelength: float,
    end_wavelength: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Stitch vendor-format captures and trim the requested range."""
    if not captures:
        raise RuntimeError("No spectra were captured for stitching.")
    stitched = LinearSpectraStitch(captures).stitched_spectra()
    x = np.asarray(stitched[0], dtype=float)
    y = np.asarray(stitched[1][0], dtype=float)
    if x.shape != y.shape:
        raise RuntimeError("Stitched wavelength and intensity shapes differ.")
    mask = (x >= start_wavelength) & (x <= end_wavelength)
    if not np.any(mask):
        raise RuntimeError("The stitched spectrum does not cover the requested range.")
    return x[mask], y[mask]


async def _center_wavelengths(
    spec: HoribaSpectrometer,
    start_wavelength: float,
    end_wavelength: float,
    stitch_pixel_overlap: int,
) -> list[float]:
    """Calculate the centre wavelengths required for a range scan.

    The HORIBA ICL range calculation CCD wavelength axis to be
    initialised before ``range_mode_center_wavelengths`` is called.
    """
    if stitch_pixel_overlap < 0:
        raise ValueError("stitch_pixel_overlap cannot be negative.")

    if start_wavelength == end_wavelength:
        raise ValueError("Start and end wavelengths must be different.")

    # Critical ordering requirement:
    # establish the mono identity, current centre wavelength, and calibrated
    # CCD x-axis before asking ICL to determine the range positions.
    current_wavelength = await spec.prepare_wavelength_axis()

    logger.debug(
        "Calculating range centres from {:.3f} to {:.3f} nm "
        "with {}-pixel overlap; current mono wavelength is {:.3f} nm",
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
        "HORIBA range calculation returned {} centre wavelength(s)",
        len(centers),
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
    """Capture one reusable stitched dark spectrum across the full range.

    At every centre wavelength, ``n_frames`` closed-shutter frames are combined.
    The stitched result can be saved and reused for hyperspectral mappings.
    """
    if end_wavelength < start_wavelength:
        start_wavelength, end_wavelength = end_wavelength, start_wavelength

    centers = await _center_wavelengths(
        spec, start_wavelength, end_wavelength, stitch_pixel_overlap
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
        x, y = await spec.get_dark_spectrum(n_frames=n_frames, mode=mode)
        captures.append([x.tolist(), [y.tolist()]])

    x_out, y_out = _stitch_and_filter(captures, start_wavelength, end_wavelength)
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
    """Acquire a stitched spectrum with selectable dark-frame behaviour.

    Dark modes
    ----------
    none:
        Acquire signal frames only.
    per_center:
        At each centre wavelength, acquire one dark and subtract it from every
        repeated signal frame before combining those signal frames.
    per_frame:
        Pair every signal frame with a new dark frame, subtract each pair, then
        combine the corrected repeated frames.
    pre_taken:
        Acquire the full range without new dark frames, then subtract a supplied
        stitched :class:`DarkSpectrum`. This is intended for repeated mappings
        made with unchanged detector and wavelength settings.
    """
    if dark_mode not in {"none", "per_center", "per_frame", "pre_taken"}:
        raise ValueError(f"Unsupported dark_mode {dark_mode!r}.")
    if dark_mode == "pre_taken" and pre_taken_dark is None:
        raise ValueError("pre_taken_dark is required for dark_mode='pre_taken'.")
    if dark_mode != "pre_taken" and pre_taken_dark is not None:
        raise ValueError("pre_taken_dark may only be used with dark_mode='pre_taken'.")
    if end_wavelength < start_wavelength:
        start_wavelength, end_wavelength = end_wavelength, start_wavelength

    centers = await _center_wavelengths(
        spec, start_wavelength, end_wavelength, stitch_pixel_overlap
    )
    logger.info("Range scan requires {} centre wavelengths", len(centers))

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
        x, y = await spec.get_spectrum(
            n_frames=n_frames,
            mode=mode,
            dark_frame_mode=frame_dark_mode,
        )
        captures.append([x.tolist(), [y.tolist()]])

    x_out, y_out = _stitch_and_filter(captures, start_wavelength, end_wavelength)
    if dark_mode == "pre_taken":
        y_out = subtract_dark_spectrum(x_out, y_out, pre_taken_dark)
    return x_out, y_out
