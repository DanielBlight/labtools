"""Plotting helpers for scanning-mirror intensity maps.

Install as ``src/labtools/visualisation/intensity_map.py``.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def plot_intensity_map(
    x_values_v: FloatArray,
    y_values_v: FloatArray,
    intensity_cps: FloatArray,
    *,
    title: str = "Intensity map",
    output_path: str | Path | None = None,
    cmap: str = "inferno",
    show: bool = True,
) -> tuple[Figure, Axes]:
    """Plot a completed or partial intensity map."""
    x_values = np.asarray(x_values_v, dtype=float)
    y_values = np.asarray(y_values_v, dtype=float)
    values = np.asarray(intensity_cps, dtype=float)
    expected = (y_values.size, x_values.size)
    if values.shape != expected:
        raise ValueError(f"intensity_cps must have shape {expected}; got {values.shape}.")

    figure, axes = plt.subplots(figsize=(7.2, 5.8))
    image = axes.imshow(
        values,
        origin="lower",
        extent=(
            float(x_values.min()),
            float(x_values.max()),
            float(y_values.min()),
            float(y_values.max()),
        ),
        aspect="auto",
        interpolation="nearest",
        cmap=cmap,
    )
    colourbar = figure.colorbar(image, ax=axes, pad=0.03)
    colourbar.set_label("Count rate (counts s$^{-1}$)")
    axes.set_xlabel("Mirror X voltage (V)")
    axes.set_ylabel("Mirror Y voltage (V)")
    axes.set_title(title)
    figure.subplots_adjust(left=0.15, right=0.87, bottom=0.13, top=0.90)

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(path, dpi=250, bbox_inches="tight")
    if show:
        plt.show()
    return figure, axes


def update_map_axes(
    axes: Axes,
    image,
    intensity_cps: FloatArray,
    *,
    title: str,
) -> None:
    """Update an existing map image without coupling plotting to acquisition."""
    values = np.asarray(intensity_cps, dtype=float)
    image.set_data(values)
    finite = values[np.isfinite(values)]
    if finite.size:
        lower = float(np.min(finite))
        upper = float(np.max(finite))
        if np.isclose(lower, upper):
            upper = lower + max(1.0, abs(lower) * 0.01)
        image.set_clim(lower, upper)
    axes.set_title(title)
    axes.figure.canvas.draw_idle()
