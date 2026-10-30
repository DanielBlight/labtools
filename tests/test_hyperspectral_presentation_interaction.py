from types import SimpleNamespace

import numpy as np
import pytest

from labtools.gui.hyperspectral_view import build_view, nearest_axis_index


def sample(mask=None):
    cube=np.arange(24,dtype=float).reshape(2,2,6)
    if mask is None: mask=np.array([[True,False],[True,True]])
    cube[~mask]=np.nan
    return SimpleNamespace(intensity=cube, completed_mask=mask,
        wavelength_nm=np.linspace(500,600,6), x_v=np.array([-1.0,1.0]),
        y_v=np.array([2.0,0.0]))

def test_nan_safe_raw_sum_masks_uncompleted_and_preserves_source():
    result=sample(); before=result.intensity.copy()
    view=build_view(result)
    assert view.integrated_intensity[0,0] == 15
    assert np.isnan(view.integrated_intensity[0,1])
    assert not view.integrated_intensity.flags.writeable
    assert not view.completed_mask.flags.writeable
    np.testing.assert_equal(result.intensity,before)

def test_zero_completion_and_selection_contracts():
    result=sample(np.zeros((2,2),dtype=bool))
    assert np.isnan(build_view(result).integrated_intensity).all()
    with pytest.raises(ValueError, match="not been completed"):
        build_view(result,0,0)
    with pytest.raises(IndexError, match="outside"):
        build_view(result,2,0)

def test_selected_spectrum_and_axes_are_read_only():
    view=build_view(sample(),1,1)
    np.testing.assert_array_equal(view.spectrum,np.arange(18,24))
    assert view.x_voltage == 1.0 and view.y_voltage == 0.0
    assert not view.spectrum.flags.writeable
    assert not view.wavelength_nm.flags.writeable

def test_coordinate_mapping_increasing_decreasing_single_and_bounds():
    assert nearest_axis_index([0,1,2],1.4)==1
    assert nearest_axis_index([2,1,0],0.6)==1
    assert nearest_axis_index([3],999)==0
    with pytest.raises(IndexError): nearest_axis_index([0,1,2],3)
    with pytest.raises(ValueError): nearest_axis_index([],0)
