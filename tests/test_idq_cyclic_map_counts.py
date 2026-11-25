"""Fixed hardware-window map counts; no hardware endpoints or Qt required."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from labtools.devices.idq_time_controller.controller import IDQTimeController
from labtools.runtime.idq_count_service import IDQCountService


@pytest.fixture
def rig(monkeypatch):
    controller = IDQTimeController("169.254.99.159")
    commands, queries, sleeps = [], [], []
    def query(command):
        queries.append(command)
        if command.endswith(":MODE?"):
            return "CYCLE\n"
        if command.endswith(":INTEgrationtime?"):
            return "120"
        return "24"
    monkeypatch.setattr(controller, "_cmd", commands.append)
    monkeypatch.setattr(controller, "_query", query)
    monkeypatch.setattr("labtools.devices.idq_time_controller.controller.time.sleep", sleeps.append)
    return controller, commands, queries, sleeps


def test_prepare_once_and_read_only_per_pixel(rig):
    controller, commands, queries, sleeps = rig
    controller.prepare_counts((1, 2), 0.12)
    assert len(commands) == 4
    for _ in range(3):
        assert controller.get_simultaneous_counts((1, 2), 0.12) == {1: 24, 2: 24}
    assert len(commands) == 4
    assert sleeps == pytest.approx([0.241] * 3)
    assert queries.count("INPU2:COUNter:INTEgrationtime?") == 1
    assert queries.count("INPU2:COUNter?") == 3
    assert all("REC:" not in c and "RESE" not in c and "ACCU" not in c for c in commands + queries)


@pytest.mark.parametrize("phase", [0.0, 0.001, 0.06, 0.119999])
@pytest.mark.parametrize("extra_delay", [0.0, 0.05, 0.7])
def test_completed_window_after_move_despite_phase_and_host_delay(monkeypatch, phase, extra_delay):
    controller = IDQTimeController("169.254.99.159")
    clock = [0.0]
    controller._cmd = lambda c: None
    def query(command):
        if command.endswith(":MODE?"):
            return "CYCLE"
        if command.endswith(":INTEgrationtime?"):
            return "120"
        # Model a latched last-completed cyclic window, phase unknown at movement.
        import math
        end = phase + math.floor((clock[0] - phase) / 0.12) * 0.12
        assert end - 0.12 >= 0.0
        return "24"  # Fixed 120 ms window, regardless of host delay.
    controller._query = query
    def sleep(duration):
        clock[0] += duration + extra_delay
    monkeypatch.setattr("labtools.devices.idq_time_controller.controller.time.sleep", sleep)
    assert controller.get_simultaneous_counts((2,), 0.12) == {2: 24}


@pytest.mark.parametrize("channels,duration", [([], .12), ([1, 1], .12), ([5], .12), ([True], .12), ([1.5], .12), ([1], 0), ([1], -1), ([1], float("nan")), ([1], float("inf"))])
def test_invalid_settings_before_io(rig, channels, duration):
    controller, commands, queries, sleeps = rig
    with pytest.raises(ValueError):
        controller.prepare_counts(channels, duration)
    assert not commands and not queries and not sleeps


@pytest.mark.parametrize("mode,actual", [("ACCU", "120"), ("CYCLE", "100"), ("CYCLE", "nan")])
def test_readback_mismatch_refused(rig, mode, actual):
    controller, _commands, _queries, sleeps = rig
    controller._query = lambda c: mode if c.endswith(":MODE?") else actual
    with pytest.raises((ValueError, RuntimeError)):
        controller.prepare_counts((2,), .12)
    assert controller._count_configuration is None
    assert not sleeps


def test_reconfigure_after_channel_configuration(rig):
    controller, commands, _queries, _sleeps = rig
    controller.prepare_counts((2,), .12)
    controller.configure_channel(2, threshold_v=.1, edge="rising")
    assert controller._count_configuration is None
    controller.prepare_counts((2,), .12)
    assert commands.count("INPU2:COUNter:MODE CYCLE") == 2


def test_service_forwards_preparation_and_rejects_after_close():
    device = Mock()
    service = IDQCountService("169.254.99.159", controller_factory=lambda a: device)
    service.prepare_counts((2,), .12)
    device.prepare_counts.assert_called_once_with((2,), .12)
    service.close()
    with pytest.raises(RuntimeError):
        service.prepare_counts((2,), .12)


def test_map_prepares_once_before_gate_and_movement(tmp_path):
    from contextlib import contextmanager

    from labtools.acquisition.intensity_map import acquire_intensity_map
    from labtools.config.intensity_map import IntensityMapConfig
    events = []
    config = IntensityMapConfig(
        x_start_v=0, x_stop_v=1, x_points=2,
        y_start_v=0, y_stop_v=1, y_points=2,
        channels=(2,), channel_thresholds_v=(.1,), channel_edges=("rising",),
        integration_time_s=.12, settle_time_s=0, backend="simulation",
        simulation_realtime=False, save_results=False, output_root=tmp_path,
    )
    mirror = SimpleNamespace(move=lambda *a: events.append("move"), home=lambda: None)
    gate = SimpleNamespace(open=lambda: events.append("gate"), close=lambda: None)
    counter = SimpleNamespace(
        configure_channel=lambda *a, **k: events.append("channel"),
        prepare_counts=lambda *a: events.append("prepare"),
        get_simultaneous_counts=lambda *a: events.append("read") or {2: 24},
    )
    @contextmanager
    def provider(config):
        yield mirror, gate, counter
    result = acquire_intensity_map(config, device_provider=provider, memory_only=True)
    assert result.complete
    assert events[:3] == ["channel", "prepare", "gate"]
    assert events.count("prepare") == 1
    assert events.count("read") == 4
    assert (result.count_rates_cps == 200).all()
