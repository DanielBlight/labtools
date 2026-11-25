"""Mirror-axis physical scale is consistent in GUI and exported maps."""

import numpy as np
import pytest

from labtools.visualisation.intensity_map import (
    MIRROR_Y_PER_X_SCALE,
    plot_intensity_map,
)

pytest_plugins = ["test_experiment_panels"]


def test_legacy_mirror_axis_scale_constant():
    assert MIRROR_Y_PER_X_SCALE == pytest.approx(0.75)


def test_exported_intensity_map_uses_calibrated_aspect(tmp_path):
    figure, axes = plot_intensity_map(
        np.array([-1.0, 1.0]),
        np.array([-1.0, 1.0]),
        np.array([[1.0, 2.0], [3.0, 4.0]]),
        show=False,
        output_path=tmp_path / "map.png",
    )
    try:
        assert float(axes.get_aspect()) == pytest.approx(MIRROR_Y_PER_X_SCALE)
        assert (tmp_path / "map.png").is_file()
    finally:
        figure.clear()


def test_live_intensity_map_uses_calibrated_aspect(window):
    _app, widget, _workspace = window
    panel = widget.pages["Intensity map"]
    assert float(panel.axes.get_aspect()) == pytest.approx(MIRROR_Y_PER_X_SCALE)
    panel._set_map_display_geometry([-2, 2], [-2, 2], (2, 2), force=True)
    assert float(panel.axes.get_aspect()) == pytest.approx(MIRROR_Y_PER_X_SCALE)
