"""Plotting and colour-normalisation helpers for scanning-mirror maps."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import LogNorm, Normalize
from matplotlib.figure import Figure
from matplotlib.image import AxesImage
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class PlotSettings:
    """Presentation settings that do not affect acquisition or resume validity."""

    use_log_scale: bool = False
    vmin_cps: float | None = None
    vmax_cps: float | None = None
    cmap: str = "inferno"

    def validate(self) -> None:
        if (self.vmin_cps is None) != (self.vmax_cps is None):
            raise ValueError("Specify both colour limits or neither.")
        if self.vmin_cps is not None and self.vmax_cps is not None:
            if self.vmax_cps <= self.vmin_cps:
                raise ValueError("The upper colour limit must exceed the lower limit.")
            if self.use_log_scale and self.vmin_cps <= 0:
                raise ValueError("Log colour scales require a positive lower limit.")

    def to_metadata(self) -> dict[str, object]:
        return asdict(self)


def _validated_values(intensity_cps: FloatArray) -> FloatArray:
    values = np.asarray(intensity_cps, dtype=float)
    if values.ndim != 2:
        raise ValueError(f"intensity_cps must be two-dimensional; got {values.shape}.")
    return values


def colour_mapping(
    intensity_cps: FloatArray,
    settings: PlotSettings,
) -> tuple[np.ndarray | np.ma.MaskedArray, Normalize]:
    """Return display values and a consistent linear or logarithmic normaliser."""
    settings.validate()
    values = _validated_values(intensity_cps)
    finite = values[np.isfinite(values)]
    positive = finite[finite > 0]

    if settings.vmin_cps is not None and settings.vmax_cps is not None:
        lower = float(settings.vmin_cps)
        upper = float(settings.vmax_cps)
    elif settings.use_log_scale:
        if positive.size:
            lower = float(np.min(positive))
            upper = float(np.max(positive))
            if np.isclose(lower, upper):
                upper = lower * 10.0
        else:
            lower, upper = 1.0, 10.0
    elif finite.size:
        lower = float(np.min(finite))
        upper = float(np.max(finite))
        if np.isclose(lower, upper):
            upper = lower + max(1.0, abs(lower) * 0.01)
    else:
        lower, upper = 0.0, 1.0

    if settings.use_log_scale:
        display = np.ma.masked_less_equal(values, 0.0)
        norm: Normalize = LogNorm(vmin=lower, vmax=upper, clip=True)
    else:
        display = values
        norm = Normalize(vmin=lower, vmax=upper, clip=True)
    return display, norm


def update_map_axes(
    axes: Axes,
    image: AxesImage,
    intensity_cps: FloatArray,
    *,
    title: str,
    settings: PlotSettings | None = None,
) -> None:
    """Update an existing image using reusable colour-normalisation logic."""
    plot_settings = settings or PlotSettings()
    display, norm = colour_mapping(intensity_cps, plot_settings)
    image.set_cmap(plot_settings.cmap)
    image.set_data(display)
    image.set_norm(norm)
    axes.set_title(title)
    axes.figure.canvas.draw_idle()


def plot_intensity_map(
    x_values_v: FloatArray,
    y_values_v: FloatArray,
    intensity_cps: FloatArray,
    *,
    title: str = "Intensity map",
    output_path: str | Path | None = None,
    settings: PlotSettings | None = None,
    show: bool = True,
) -> tuple[Figure, Axes]:
    """Plot a completed or partial map using the same settings as the GUI."""
    x_values = np.asarray(x_values_v, dtype=float)
    y_values = np.asarray(y_values_v, dtype=float)
    values = _validated_values(intensity_cps)
    expected = (y_values.size, x_values.size)
    if values.shape != expected:
        raise ValueError(
            f"intensity_cps must have shape {expected}; got {values.shape}."
        )

    plot_settings = settings or PlotSettings()
    display, norm = colour_mapping(values, plot_settings)
    figure, axes = plt.subplots(figsize=(7.2, 5.8))
    image = axes.imshow(
        display,
        origin="lower",
        extent=(
            float(x_values.min()),
            float(x_values.max()),
            float(y_values.min()),
            float(y_values.max()),
        ),
        aspect="auto",
        interpolation="nearest",
        cmap=plot_settings.cmap,
        norm=norm,
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
