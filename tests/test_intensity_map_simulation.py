"""Offline tests of the real acquisition loop with simulated devices."""
from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from labtools.acquisition.intensity_map import (
    CHECKPOINT_FILENAME, METADATA_FILENAME, IntensityMapConfig,
    acquire_intensity_map, config_from_resume_directory,
)
from labtools.simulation.map_backend import open_map_devices


@pytest.fixture
def config(tmp_path):
    return IntensityMapConfig(
        x_start_v=-1., x_stop_v=1., x_points=5,
        y_start_v=-1., y_stop_v=1., y_points=5,
        channels=(1, 2), channel_thresholds_v=(.1, .1),
        channel_edges=('rising', 'falling'), integration_time_s=.02,
        settle_time_s=0., output_root=tmp_path,
        backend='simulation', simulation_seed=42,
        simulation_realtime=False, save_results=False,
        checkpoint_every_points=2,
    )


@pytest.fixture(autouse=True)
def no_native_imports(monkeypatch):
    original = builtins.__import__
    blocked = ('u6', 'LabJackPython', 'pyvisa', 'zmq', 'pyft232', 'pylablib', 'labtools.devices')
    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + '.') for prefix in blocked):
            raise AssertionError('Hardware import forbidden in simulation: ' + name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)


def test_complete_two_channel_map(config):
    result = acquire_intensity_map(config)
    assert result.complete
    assert result.counts.shape == (2, 5, 5)
    assert result.completed_mask.all()
    assert np.all(result.counts >= 0)
    np.testing.assert_allclose(result.summed_count_rate_cps, result.count_rates_cps.sum(axis=0))
    assert result.output_directory.parent.name == 'SIMULATION'
    assert (result.output_directory / 'SYNTHETIC_DATA.txt').exists()
    metadata = json.loads((result.output_directory / METADATA_FILENAME).read_text())
    assert metadata['synthetic_data'] is True
    assert metadata['backend'] == 'simulation'


def test_position_changes_counts_and_gate(config):
    with open_map_devices(config) as (mirror, gate, counter):
        counter.configure_channel(1, threshold_v=.1, edge='rising')
        mirror.move(0., 0.)
        assert counter.get_simultaneous_counts((1,), .1)[1] == 0
        gate.open()
        centre = counter.get_simultaneous_counts((1,), .1)[1]
        mirror.move(-1., -1.)
        corner = counter.get_simultaneous_counts((1,), .1)[1]
        assert centre > corner
        state = mirror.state
    assert state.closed and not state.gate_open


def test_stop_and_resume_matches_uninterrupted(config):
    latest = [0]
    def progress(snapshot):
        latest[0] = snapshot.points_complete
    partial = acquire_intensity_map(config, progress_callback=progress,
                                    cancel_requested=lambda: latest[0] >= 7)
    assert not partial.complete
    assert partial.completed_mask.sum() == 7
    assert (partial.output_directory / CHECKPOINT_FILENAME).exists()
    restored = config_from_resume_directory(partial.output_directory)
    assert restored.backend == 'simulation'
    resumed = acquire_intensity_map(restored, resume_directory=partial.output_directory)
    assert resumed.complete and resumed.resumed
    np.testing.assert_array_equal(resumed.counts[:, partial.completed_mask], partial.counts[:, partial.completed_mask])
    np.testing.assert_array_equal(resumed.session_ids[partial.completed_mask], partial.session_ids[partial.completed_mask])
    fresh = acquire_intensity_map(replace(config, output_root=config.output_root / 'fresh'))
    np.testing.assert_array_equal(resumed.counts, fresh.counts)


def test_failure_retains_checkpoint_and_resume(config):
    failed = replace(config, simulation_fail_after_points=4)
    with pytest.raises(TimeoutError, match='SIMULATION'):
        acquire_intensity_map(failed)
    directory = next((config.output_root / 'SIMULATION').iterdir())
    with np.load(directory / CHECKPOINT_FILENAME) as checkpoint:
        assert checkpoint['completed_mask'].sum() == 4
    restored = replace(config_from_resume_directory(directory), simulation_fail_after_points=None)
    assert acquire_intensity_map(restored, resume_directory=directory).complete


def test_cross_backend_resume_rejected_before_hardware(config):
    partial = acquire_intensity_map(config, cancel_requested=lambda: True)
    with pytest.raises(ValueError, match='backend'):
        acquire_intensity_map(replace(config, backend='real'), resume_directory=partial.output_directory)


def test_changed_seed_resume_rejected(config):
    partial = acquire_intensity_map(config, cancel_requested=lambda: True)
    with pytest.raises(ValueError, match='simulation_seed'):
        acquire_intensity_map(replace(config, simulation_seed=999), resume_directory=partial.output_directory)


@pytest.mark.parametrize('backend', ['invalid', '', 'SIMULATION'])
def test_invalid_backend(config, backend):
    with pytest.raises(ValueError, match='backend'):
        replace(config, backend=backend).validate()


@pytest.mark.parametrize('seed', [-1, 1.5, True])
def test_invalid_seed(config, seed):
    with pytest.raises(ValueError, match='seed'):
        replace(config, simulation_seed=seed).validate()


def test_no_fallback_on_real_failure(config):
    with pytest.raises(AssertionError, match='Hardware import forbidden'):
        with open_map_devices(replace(config, backend='real')):
            pytest.fail('Real backend unexpectedly connected')


def test_single_channel(config):
    single = replace(config, channels=(3,), channel_thresholds_v=(.1,), channel_edges=('rising',))
    result = acquire_intensity_map(single)
    assert result.counts.shape == (1, 5, 5)
    np.testing.assert_allclose(result.summed_count_rate_cps, result.count_rates_cps[0])


def test_final_outputs_labelled(config):
    result = acquire_intensity_map(replace(config, save_results=True))
    with np.load(result.output_directory / 'intensity_map_complete.npz') as data:
        assert data['synthetic_data'].item() is True
        assert data['backend'].item() == 'simulation'
    assert (result.output_directory / 'summed_intensity_map.png').exists()


def test_import_isolation_in_fresh_interpreter(tmp_path):
    # Block native imports before importing any labtools acquisition code.
    code = '''
import importlib.abc
import sys
from pathlib import Path
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('labtools.devices', 'u6', 'LabJackPython', 'pyvisa', 'zmq', 'pylablib', 'pyft232')):
            raise AssertionError('Native import attempted: ' + fullname)
sys.meta_path.insert(0, Block())
from labtools.acquisition.intensity_map import IntensityMapConfig, acquire_intensity_map
c = IntensityMapConfig(x_start_v=-1., x_stop_v=1., x_points=2,
    y_start_v=-1., y_stop_v=1., y_points=2, backend='simulation',
    simulation_realtime=False, settle_time_s=0., save_results=False,
    output_root=Path(sys.argv[1]))
assert acquire_intensity_map(c).complete
'''
    env = os.environ.copy()
    env['MPLBACKEND'] = 'Agg'
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    completed = subprocess.run([sys.executable, '-c', code, str(tmp_path)], env=env,
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def gui_method(name):
    import ast
    import copy
    source = Path(__file__).resolve().parents[1] / 'src/labtools/gui/intensity_map_gui.py'
    cls = next(n for n in ast.parse(source.read_text(encoding='utf-8-sig')).body
               if isinstance(n, ast.ClassDef) and n.name == 'IntensityMapWindow')
    method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name))
    method.decorator_list = []
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    ns = {'Path': Path}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, method], type_ignores=[])), str(source), 'exec'), ns)
    return ns[name]


@pytest.mark.parametrize('name', ['connect_laser', 'turn_laser_on', 'turn_laser_off', 'set_laser_current'])
def test_simulation_laser_actions_are_guarded(name):
    from types import SimpleNamespace
    messages = []
    window = SimpleNamespace(simulation_mode=SimpleNamespace(isChecked=lambda: True), set_status=messages.append)
    gui_method(name)(window)
    assert 'disabled' in messages[-1]


def test_legacy_real_signature_unchanged(config):
    signature = replace(config, backend='real').checkpoint_signature()
    assert 'backend' not in signature
    assert 'simulation_seed' not in signature
