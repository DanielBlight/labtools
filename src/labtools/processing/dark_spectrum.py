"""Reusable dark data and subtraction, independent of Qt and native drivers.

CSV parsing and array ownership retain existing behaviour. This is not a
calibration/provenance validator for deciding whether a dark can be reused.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np

@dataclass(frozen=True)
class DarkSpectrum:
    """Reusable stitched dark spectrum on a wavelength axis."""

    wavelength_nm: np.ndarray
    intensity: np.ndarray

    def __post_init__(self) -> None:
        x_data = np.asarray(self.wavelength_nm, dtype=float)
        y_data = np.asarray(self.intensity, dtype=float)

        if x_data.ndim != 1 or y_data.ndim != 1 or x_data.shape != y_data.shape:
            raise ValueError("DarkSpectrum arrays must be matching 1D arrays.")
        if x_data.size == 0:
            raise ValueError("DarkSpectrum cannot be empty.")
        if not np.all(np.isfinite(x_data)) or not np.all(np.isfinite(y_data)):
            raise ValueError("DarkSpectrum values must be finite.")

        object.__setattr__(self, "wavelength_nm", x_data)
        object.__setattr__(self, "intensity", y_data)

    def save_csv(self, path: str | Path) -> None:
        """Save wavelength and dark intensity as a two-column CSV."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = np.column_stack((self.wavelength_nm, self.intensity))
        np.savetxt(
            output_path,
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
            x_data = np.asarray(data[data.dtype.names[0]], dtype=float)
            y_data = np.asarray(data[data.dtype.names[1]], dtype=float)
        else:
            plain = np.loadtxt(path, delimiter=",", ndmin=2)
            if plain.shape[1] < 2:
                raise ValueError("Dark CSV must contain at least two columns.")
            x_data = plain[:, 0]
            y_data = plain[:, 1]

        return cls(x_data, y_data)


def subtract_dark_spectrum(
    wavelength_nm: np.ndarray,
    intensity: np.ndarray,
    dark: DarkSpectrum,
    *,
    wavelength_tolerance_nm: float = 1e-8,
) -> np.ndarray:
    """Subtract a reusable dark after validating its wavelength axis."""
    x_data = np.asarray(wavelength_nm, dtype=float)
    y_data = np.asarray(intensity, dtype=float)

    if x_data.shape != y_data.shape:
        raise ValueError("Signal wavelength and intensity shapes differ.")

    if dark.wavelength_nm.shape != x_data.shape or not np.allclose(
        dark.wavelength_nm,
        x_data,
        rtol=0.0,
        atol=wavelength_tolerance_nm,
    ):
        raise ValueError(
            "Pre-taken dark wavelength values do not match this range spectrum. "
            "Use the same range, overlap, detector, ROI, grating, and calibration."
        )

    return y_data - dark.intensity


