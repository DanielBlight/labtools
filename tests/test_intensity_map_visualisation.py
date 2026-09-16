"""Hardware-free tests for intensity-map colour normalisation."""

from __future__ import annotations

import numpy as np
import pytest
from matplotlib.colors import LogNorm, Normalize

from labtools.visualisation.intensity_map import PlotSettings, colour_mapping


def test_linear_colour_mapping_uses_full_finite_range() -> None:
    values = np.array([[1.0, 2.0], [3.0, np.nan]])
    display, norm = colour_mapping(values, PlotSettings())
    assert isinstance(norm, Normalize)
    assert not isinstance(norm, LogNorm)
    assert norm.vmin == pytest.approx(1.0)
    assert norm.vmax == pytest.approx(3.0)
    assert np.asarray(display).shape == values.shape


def test_log_colour_mapping_masks_non_positive_values() -> None:
    values = np.array([[0.0, 1.0], [10.0, -2.0]])
    display, norm = colour_mapping(values, PlotSettings(use_log_scale=True))
    assert isinstance(norm, LogNorm)
    assert bool(display.mask[0, 0])
    assert bool(display.mask[1, 1])
    assert norm.vmin == pytest.approx(1.0)
    assert norm.vmax == pytest.approx(10.0)


def test_manual_log_limits_require_positive_lower_limit() -> None:
    settings = PlotSettings(use_log_scale=True, vmin_cps=0.0, vmax_cps=100.0)
    with pytest.raises(ValueError, match="positive lower limit"):
        colour_mapping(np.ones((2, 2)), settings)
