"""Qt-free, deterministic, read-only hyperspectral presentation transforms."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HyperspectralView:
    integrated_intensity: np.ndarray
    completed_mask: np.ndarray
    wavelength_nm: np.ndarray
    spectrum: np.ndarray | None
    y_index: int | None
    x_index: int | None
    x_voltage: float | None = None
    y_voltage: float | None = None


def _readonly_copy(value, *, dtype=None):
    result = np.array(value, dtype=dtype, copy=True)
    result.setflags(write=False)
    return result


def build_view(result, y_index: int | None = None, x_index: int | None = None):
    """Build a safe view using the compatibility-preserving NaN-safe raw sum."""
    cube = np.asarray(result.intensity)
    mask = np.asarray(result.completed_mask, dtype=bool)
    wavelength = np.asarray(result.wavelength_nm)
    if cube.ndim != 3:
        raise ValueError("Hyperspectral intensity must be a three-dimensional cube")
    if mask.shape != cube.shape[:2]:
        raise ValueError("Completed mask shape does not match the hyperspectral cube")
    if wavelength.ndim != 1 or wavelength.size != cube.shape[2]:
        raise ValueError("Wavelength axis length does not match the spectral dimension")
    integrated = np.nansum(cube, axis=2)
    integrated = np.where(mask, integrated, np.nan)
    integrated = _readonly_copy(integrated)
    mask_out = _readonly_copy(mask, dtype=bool)
    wavelength_out = _readonly_copy(wavelength)
    spectrum = None
    xv = yv = None
    if (y_index is None) != (x_index is None):
        raise ValueError("Both X and Y indices are required")
    if y_index is not None:
        if not (0 <= y_index < mask.shape[0] and 0 <= x_index < mask.shape[1]):
            raise IndexError("Selected pixel is outside the hyperspectral map")
        if not mask[y_index, x_index]:
            raise ValueError("Selected pixel has not been completed")
        spectrum = _readonly_copy(cube[y_index, x_index])
        if hasattr(result, "x_v") and hasattr(result, "y_v"):
            xv = float(np.asarray(result.x_v)[x_index])
            yv = float(np.asarray(result.y_v)[y_index])
    return HyperspectralView(integrated, mask_out, wavelength_out, spectrum,
                             y_index, x_index, xv, yv)


def nearest_axis_index(axis, coordinate: float) -> int:
    """Map a finite plot coordinate to the nearest element of any finite 1-D axis."""
    values = np.asarray(axis, dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("Voltage axis is empty or malformed")
    if not np.isfinite(coordinate) or not np.all(np.isfinite(values)):
        raise ValueError("Voltage coordinates must be finite")
    if values.size == 1:
        return 0
    lo, hi = sorted((float(values[0]), float(values[-1])))
    half = abs(float(values[-1] - values[0])) / (2 * (values.size - 1))
    if coordinate < lo - half or coordinate > hi + half:
        raise IndexError("Click is outside the hyperspectral map")
    return int(np.argmin(np.abs(values - coordinate)))
