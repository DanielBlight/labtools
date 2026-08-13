"""Pure helper functions for background/dark-frame subtraction in the GUI.

These are deliberately Qt-free so they can be unit tested without a running
QApplication. The GUI is responsible for file dialogs and status messages;
this module only parses data and does the subtraction math.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

_WAVELENGTH_HEADER_TOKENS = {"wavelength", "wl", "x", "x_data"}


def parse_background_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse a two-column (wavelength, intensity) background CSV.

    Parameters
    ----------
    path : str or Path
        Path to the CSV file. An optional header row is detected and skipped
        if its first cell looks like a wavelength column label.

    Returns
    -------
    x_values : numpy.ndarray
        Wavelength axis (nm).
    y_values : numpy.ndarray
        Intensity values.

    Raises
    ------
    ValueError
        If the file is empty or does not contain any wavelength/intensity pairs.
    """
    with open(path, newline="") as fh:
        rows = [row for row in csv.reader(fh) if row and not all(cell.strip() == "" for cell in row)]
    if not rows:
        raise ValueError("Background CSV is empty.")

    start_index = 0
    if len(rows[0]) >= 2 and rows[0][0].strip().lower() in _WAVELENGTH_HEADER_TOKENS:
        start_index = 1

    data = []
    for row in rows[start_index:]:
        if len(row) < 2:
            continue
        data.append((float(row[0]), float(row[1])))
    if not data:
        raise ValueError("Background CSV does not contain wavelength, intensity pairs.")

    x_vals, y_vals = zip(*data)
    return np.asarray(x_vals, dtype=float), np.asarray(y_vals, dtype=float)


def apply_background_subtraction(
    x_data: np.ndarray,
    y_data: np.ndarray,
    background_spectrum: tuple[np.ndarray, np.ndarray] | None,
) -> np.ndarray:
    """Subtract a background spectrum from acquired data.

    Parameters
    ----------
    x_data : numpy.ndarray
        Wavelength axis of the acquired spectrum.
    y_data : numpy.ndarray
        Intensity values of the acquired spectrum.
    background_spectrum : tuple of (numpy.ndarray, numpy.ndarray) or None
        ``(background_x, background_y)`` previously loaded/captured. The
        wavelength axis must match ``x_data`` exactly.

    Returns
    -------
    numpy.ndarray
        ``y_data - background_y``.

    Raises
    ------
    ValueError
        If no background spectrum is available, or its wavelength axis does
        not match ``x_data``.
    """
    if background_spectrum is None:
        raise ValueError("No background spectrum available. Capture a dark frame or load a background CSV first.")

    bg_x, bg_y = background_spectrum
    x_arr = np.asarray(x_data)
    if bg_x.shape != x_arr.shape or not np.allclose(bg_x, x_arr, rtol=0, atol=1e-8):
        raise ValueError("Background wavelength values must be identical to the acquired spectrum wavelength values.")

    return np.asarray(y_data, dtype=float) - np.asarray(bg_y, dtype=float)
