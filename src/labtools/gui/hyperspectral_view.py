"""Qt-free read-only transformations for hyperspectral GUI presentation."""

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


def build_view(result, y_index: int | None = None, x_index: int | None = None):
    cube = result.intensity
    integrated = np.nansum(cube, axis=2) if cube.ndim == 3 else np.empty((0, 0))
    integrated.setflags(write=False)
    mask = result.completed_mask
    spectrum = None
    if y_index is not None and x_index is not None:
        if not (0 <= y_index < mask.shape[0] and 0 <= x_index < mask.shape[1]):
            raise IndexError("Selected pixel is outside the hyperspectral map")
        if not mask[y_index, x_index]:
            raise ValueError("Selected pixel has not been completed")
        spectrum = cube[y_index, x_index]
    return HyperspectralView(
        integrated, mask, result.wavelength_nm, spectrum, y_index, x_index
    )
