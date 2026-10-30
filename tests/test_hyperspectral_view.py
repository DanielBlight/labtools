from types import SimpleNamespace

import numpy as np
import pytest

from labtools.gui.hyperspectral_view import build_view


def result(completed=True):
    cube = np.arange(24, dtype=float).reshape(2, 2, 6)
    cube.setflags(write=False)
    mask = np.array([[completed, False], [True, True]])
    mask.setflags(write=False)
    wl = np.linspace(500, 600, 6)
    wl.setflags(write=False)
    return SimpleNamespace(intensity=cube, completed_mask=mask, wavelength_nm=wl)


def test_integrated_and_selected_spectrum_are_read_only():
    view = build_view(result(), 0, 0)
    assert view.integrated_intensity.shape == (2, 2)
    assert not view.integrated_intensity.flags.writeable
    assert np.array_equal(view.spectrum, np.arange(6))


def test_uncompleted_and_outside_pixels_rejected():
    with pytest.raises(ValueError):
        build_view(result(), 0, 1)
    with pytest.raises(IndexError):
        build_view(result(), 9, 0)
