"""Offline spectrum math, real acquisition methods, and range sequencing.

Method extraction avoids loading native drivers. Range tests replace only the
vendor stitch boundary; they do not validate the installed HORIBA stitcher.
"""
import ast
import asyncio
import copy
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from labtools.processing.spectrum import combine_frames
from labtools.processing.dark_spectrum import DarkSpectrum, subtract_dark_spectrum
from labtools.acquisition import range_spectrum as ranges

ROOT = Path(__file__).resolve().parents[1]


def method(name):
    path = ROOT / 'src/labtools/devices/horiba_spectrometer.py'
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    node = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name))
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    ns = {'np': np, 'combine_frames': combine_frames}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, node], type_ignores=[])), str(path), 'exec'), ns)
    return ns[name]


@pytest.mark.parametrize('mode', ['single', 'mean', 'median', 'sigma_clip'])
@pytest.mark.parametrize('k', [1., 3.])
def test_combination_matches_historical_algorithm(mode, k):
    frames = [np.array([1., 5., 7.]), np.array([2., 5., 8.]), np.array([100., 5., 9.])]
    stack = np.stack(frames)
    expected = {'single': frames[0], 'mean': stack.mean(0), 'median': np.median(stack, axis=0)}
    if mode == 'sigma_clip':
        mask = np.abs(stack - stack.mean(0)) > k * stack.std(0)
        target = np.nanmean(np.where(mask, np.nan, stack), axis=0)
    else:
        target = expected[mode]
    np.testing.assert_array_equal(combine_frames(frames, mode, k), target)
    np.testing.assert_array_equal(frames[0], [1., 5., 7.])


def test_single_preserves_array_identity():
    frame = np.array([2.])
    assert combine_frames([frame], 'single') is frame


@pytest.mark.parametrize('dark_mode,expected', [
    ('none', [True, True, True]),
    ('once', [False, True, True, True]),
    ('single', [False, True, True, True]),
    ('per_frame', [False, True, False, True, False, True]),
])
@pytest.mark.parametrize('mode', ['mean', 'median', 'sigma_clip'])
def test_real_signal_method_dark_order(dark_mode, expected, mode):
    calls = []
    async def acquire(*, open_shutter):
        calls.append(open_shutter)
        return np.array([500., 501.]), np.array([10., 20.]) if open_shutter else np.array([1., 2.])
    async def ready(): return True
    fake = SimpleNamespace(_exposure_time=.1, _acquire_single=acquire,
                           ccd=SimpleNamespace(get_acquisition_ready=ready))
    x, y = asyncio.run(method('get_spectrum')(fake, n_frames=3, mode=mode, dark_frame_mode=dark_mode))
    assert calls == expected
    np.testing.assert_array_equal(x, [500., 501.])
    np.testing.assert_array_equal(y, [10., 20.] if dark_mode == 'none' else [9., 18.])


@pytest.mark.parametrize('mode,n', [('single', 1), ('mean', 2), ('median', 3), ('sigma_clip', 3)])
def test_real_dark_method_never_opens_shutter(mode, n):
    calls = []
    async def acquire(*, open_shutter):
        calls.append(open_shutter)
        return np.array([500.]), np.array([2.])
    fake = SimpleNamespace(_exposure_time=.1, _acquire_single=acquire)
    _, y = asyncio.run(method('get_dark_spectrum')(fake, n_frames=n, mode=mode))
    assert calls == [False] * n
    np.testing.assert_array_equal(y, [2.])


@pytest.mark.parametrize('name', ['get_spectrum', 'get_dark_spectrum'])
@pytest.mark.parametrize('mode,n', [('bad', 1), ('single', 2), ('median', 2), ('sigma_clip', 2)])
def test_invalid_mode_or_repeat_rejected_before_capture(name, mode, n):
    async def forbidden(**kw): pytest.fail('must not acquire')
    fake = SimpleNamespace(_exposure_time=.1, _acquire_single=forbidden)
    with pytest.raises(ValueError):
        asyncio.run(method(name)(fake, n_frames=n, mode=mode))


@pytest.mark.parametrize('mode,frame_mode', [('none', 'none'), ('per_center', 'once'), ('per_frame', 'per_frame'), ('pre_taken', 'none')])
def test_range_routes_dark_mode_and_preserves_centre_order(monkeypatch, mode, frame_mode):
    calls = []
    async def centers(spec, start, end, overlap):
        assert (start, end, overlap) == (500., 502., 20)
        return [501., 502.]
    async def move(center): calls.append(('move', center)); return center
    async def capture(**kw):
        calls.append(('capture', kw))
        return np.array([500., 501., 502.]), np.array([10., 20., 30.])
    def stitch(captures, start, end):
        assert len(captures) == 2
        return np.array([500., 501., 502.]), np.array([10., 20., 30.])
    monkeypatch.setattr(ranges, '_center_wavelengths', centers)
    monkeypatch.setattr(ranges, '_stitch_and_filter', stitch)
    fake = SimpleNamespace(set_wavelength=move, get_spectrum=capture)
    dark = DarkSpectrum(np.array([500., 501., 502.]), np.ones(3)) if mode == 'pre_taken' else None
    _, y = asyncio.run(ranges.get_range_spectrum(fake, 502., 500., n_frames=3, mode='mean', dark_mode=mode, pre_taken_dark=dark))
    assert [c[0] for c in calls] == ['move', 'capture', 'move', 'capture']
    assert [c[1] for c in calls if c[0] == 'move'] == [501., 502.]
    for _, kw in calls[1::2]:
        assert kw == dict(n_frames=3, mode='mean', dark_frame_mode=frame_mode)
    np.testing.assert_array_equal(y, [9., 19., 29.] if dark is not None else [10., 20., 30.])


@pytest.mark.parametrize('mode,dark', [('bad', None), ('pre_taken', None), ('none', DarkSpectrum(np.array([500.]), np.array([1.])))])
def test_bad_range_dark_options_fail_before_device_use(mode, dark):
    with pytest.raises(ValueError):
        asyncio.run(ranges.get_range_spectrum(object(), 500., 501., dark_mode=mode, pre_taken_dark=dark))


def test_reusable_dark_capture_order(monkeypatch):
    calls = []
    async def centers(*a): return [500., 501.]
    async def move(center): calls.append(('move', center)); return center
    async def dark(**kw):
        calls.append(('dark', kw))
        return np.array([500., 501.]), np.array([1., 2.])
    monkeypatch.setattr(ranges, '_center_wavelengths', centers)
    monkeypatch.setattr(ranges, '_stitch_and_filter', lambda *a: (np.array([500., 501.]), np.array([1., 2.])))
    result = asyncio.run(ranges.capture_range_dark(SimpleNamespace(set_wavelength=move, get_dark_spectrum=dark), 501., 500., n_frames=3, mode='median'))
    assert isinstance(result, DarkSpectrum)
    assert [c[0] for c in calls] == ['move', 'dark', 'move', 'dark']
    assert calls[1][1] == {'n_frames': 3, 'mode': 'median'}


def test_dark_roundtrip_and_compatibility(tmp_path):
    assert ranges.DarkSpectrum is DarkSpectrum
    assert ranges.subtract_dark_spectrum is subtract_dark_spectrum
    original = DarkSpectrum(np.array([500., 501.]), np.array([2., 3.]))
    path = tmp_path / 'dark.csv'
    original.save_csv(path)
    restored = DarkSpectrum.load_csv(path)
    np.testing.assert_array_equal(subtract_dark_spectrum(restored.wavelength_nm, np.array([10., 20.]), restored), [8., 17.])
    with pytest.raises(ValueError):
        subtract_dark_spectrum(restored.wavelength_nm + 1, np.ones(2), restored)


@pytest.mark.parametrize('x,y', [([], []), ([1.], [1., 2.]), ([float('nan')], [1.]), ([1.], [float('inf')])])
def test_invalid_dark_arrays(x, y):
    with pytest.raises(ValueError): DarkSpectrum(np.array(x), np.array(y))


def test_imports_are_offline_and_do_not_create_output(tmp_path):
    code = r'''
import importlib.abc, os, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('labtools.devices', 'horiba_sdk', 'PyQt6', 'matplotlib', 'pandas', 'xarray', 'u6', 'pyvisa')):
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Block())
from labtools.processing.spectrum import combine_frames
from labtools.processing.dark_spectrum import DarkSpectrum
from labtools.acquisition.range_spectrum import DarkSpectrum as OldDark
from labtools.acquisition import run_hyperspectral_scan as runner
assert OldDark is DarkSpectrum
assert runner.OUTPUT_FOLDER is None
assert os.listdir('.') == []
'''
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
    result = subprocess.run([sys.executable, '-c', code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
