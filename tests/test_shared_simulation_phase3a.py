"""Phase 3a shared synthetic mirror/map state with no native device imports."""

from __future__ import annotations

import builtins
from dataclasses import replace

import numpy as np
import pytest

from labtools.acquisition.intensity_map import config_from_resume_directory
from labtools.config.intensity_map import SCHEMA_VERSION, IntensityMapConfig
from labtools.runtime.session import ResourceBusyError
from labtools.runtime.shared_application import SharedMirrorMapApplication
from labtools.simulation.map_devices import MODEL_VERSION


@pytest.fixture(autouse=True)
def no_native_imports(monkeypatch):
    original = builtins.__import__
    blocked = ("u6", "LabJackPython", "pyvisa", "zmq", "pylablib")

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in blocked):
            raise AssertionError(
                "Native import forbidden in shared simulation: " + name
            )
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


@pytest.fixture
def config(tmp_path):
    return IntensityMapConfig(
        x_start_v=-1.0,
        x_stop_v=1.0,
        x_points=3,
        y_start_v=-1.0,
        y_stop_v=1.0,
        y_points=3,
        channels=(1, 2),
        channel_thresholds_v=(0.1, 0.1),
        channel_edges=("rising", "falling"),
        integration_time_s=0.01,
        settle_time_s=0.0,
        output_root=tmp_path,
        backend="simulation",
        simulation_seed=42,
        simulation_realtime=False,
        save_results=False,
        checkpoint_every_points=1,
    )


def test_manual_map_manual_share_one_state(config):
    app = SharedMirrorMapApplication(backend="simulation")
    assert app.simulation_status().moves == 0
    app.manual_mirror.connect()
    assert app.simulation_status().moves == 0
    app.manual_mirror.move(0.5, -0.25)
    app.manual_mirror.disconnect()
    before = app.simulation_status()
    assert (before.x_v, before.y_v) == (0.5, -0.25)
    result = app.map_acquisition(config)
    assert result.complete and result.counts.shape == (2, 3, 3)
    after = app.simulation_status()
    assert after.measurements == 9
    assert (after.x_v, after.y_v) == (0.0, 0.0)
    assert not after.gate_open and not after.closed
    app.manual_mirror.connect()
    app.manual_mirror.move(-0.5, 0.25)
    app.manual_mirror.disconnect()
    app.close()
    assert app.simulation_status().closed


def test_manual_reservation_blocks_map_without_state_change(config):
    app = SharedMirrorMapApplication(backend="simulation")
    app.manual_mirror.connect()
    baseline = app.simulation_status()
    with pytest.raises(ResourceBusyError):
        app.map_acquisition(config)
    assert app.simulation_status() == baseline
    assert not app.status().resources[0].faulted
    app.manual_mirror.disconnect()
    assert app.map_acquisition(config).complete
    app.close()


def test_map_reservation_blocks_manual_and_shutdown(config):
    app = SharedMirrorMapApplication(backend="simulation")
    lease = app.session.reserve("intensity-map", ("mirror", "gate"))
    with pytest.raises(ResourceBusyError):
        app.manual_mirror.connect()
    with pytest.raises(ResourceBusyError):
        app.close()
    lease.release()
    app.close()
    assert app.simulation_status().closed


def test_determinism_and_signature_contract(config):
    first = SharedMirrorMapApplication(backend="simulation")
    second = SharedMirrorMapApplication(backend="simulation")
    a = first.map_acquisition(config)
    b = second.map_acquisition(replace(config, output_root=config.output_root / "two"))
    np.testing.assert_array_equal(a.counts, b.counts)
    signature = config.checkpoint_signature()
    assert SCHEMA_VERSION == 1
    assert MODEL_VERSION == "gaussian-scene-v1"
    assert signature["simulation_model"] == MODEL_VERSION
    assert signature["simulation_seed"] == 42
    first.close()
    second.close()


def test_shared_stop_resume_matches_uninterrupted(config):
    uninterrupted_app = SharedMirrorMapApplication(backend="simulation")
    interrupted_app = SharedMirrorMapApplication(backend="simulation")
    uninterrupted = uninterrupted_app.map_acquisition(config)
    points = [0]

    def progress(snapshot):
        points[0] = snapshot.points_complete

    partial = interrupted_app.map_acquisition(
        replace(config, output_root=config.output_root / "resume"),
        progress_callback=progress,
        cancel_requested=lambda: points[0] >= 4,
    )
    assert not partial.complete
    restored = config_from_resume_directory(partial.output_directory)
    resumed = interrupted_app.map_acquisition(
        restored, resume_directory=partial.output_directory
    )
    np.testing.assert_array_equal(uninterrupted.counts, resumed.counts)
    np.testing.assert_array_equal(uninterrupted.completed_mask, resumed.completed_mask)
    uninterrupted_app.close()
    interrupted_app.close()


def test_real_mode_has_no_simulation_status_and_no_fallback():
    created = []

    def fail():
        created.append(True)
        raise OSError("real connection failed")

    app = SharedMirrorMapApplication(backend="real", service_factory=fail)
    assert app.simulation_status() is None
    app.manual_mirror.connect()
    with pytest.raises(OSError, match="real connection failed"):
        app.manual_mirror.move(0.0, 0.0)
    assert created == [True]
    app.manual_mirror.disconnect()
    app.close()
