"""Consolidated fake-device regression tests; no device construction or I/O."""
from dataclasses import replace

import pytest

from labtools.acquisition import laser_anneal as anneal
from labtools.devices.labjack_u6 import LabJackU6
from labtools.devices.sc10 import SC10


@pytest.fixture
def rig(monkeypatch, tmp_path):
    events = []
    primary = ValueError("scan failed")
    close_error = OSError("device close failed")

    class Jack:
        __exit__ = LabJackU6.__exit__

        def __enter__(self):
            return self

        def close(self):
            events.append("labjack exit")
            if self.fail:
                raise close_error

        fail = False

    class Shutter:
        __exit__ = SC10.__exit__
        fail_close = False
        fail_exit = False
        fail_setup = False

        def __init__(self, **kwargs):
            if self.fail_setup:
                raise primary

        def __enter__(self):
            return self

        def set_mode(self, mode):
            pass

        def set_enabled(self, enabled):
            events.append("open" if enabled else "close")
            if not enabled and "open" in events and self.fail_close:
                raise close_error

        def close(self):
            events.append("sc10 exit")
            if self.fail_exit:
                raise close_error

    class Mirror:
        fail_scan = False

        def __init__(self, *args, **kwargs):
            self.moves = 0

        def move(self, x, y):
            self.moves += 1
            if (x, y) == (0.25, -0.5):
                events.append("home")
            else:
                events.append("move")
                if self.moves == 2 and self.fail_scan:
                    raise primary

    monkeypatch.setattr(anneal, "LabJackU6", Jack)
    monkeypatch.setattr(anneal, "SC10", Shutter)
    monkeypatch.setattr(anneal, "ScanningMirror", Mirror)
    config = anneal.LaserAnnealConfig(
        x_points=1, y_points=1, point_dwell_s=0, mirror_settle_s=0,
        home_x_voltage_v=0.25, home_y_voltage_v=-0.5,
        output_root=tmp_path, save_run_log=False,
    )
    return config, events, Jack, Shutter, Mirror, primary, close_error


def test_reporting_failures_cannot_prevent_cleanup(rig):
    config, events, _, _, _, _, _ = rig

    def broken_status(message):
        raise RuntimeError("reporting failed")

    result = anneal._run_laser_anneal_without_rotation_stage(
        config, status_callback=broken_status
    )
    assert result.completed
    assert events == ["close", "move", "open", "move", "close", "sc10 exit", "home", "labjack exit"]


def test_failed_close_reports_uncertain_state_and_preserves_motion_baseline(rig):
    config, events, _, shutter, _, _, _ = rig
    shutter.fail_close = True
    statuses = []
    with pytest.raises(ExceptionGroup):
        anneal._run_laser_anneal_without_rotation_stage(config, status_callback=statuses.append)
    assert statuses[-1] == "Cleanup incomplete: shutter state uncertain"
    assert events[-3:] == ["sc10 exit", "home", "labjack exit"]


@pytest.mark.parametrize("failed_exit", ["sc10", "labjack"])
def test_production_exit_preserves_exact_primary_and_cleanup_identity(rig, failed_exit):
    config, events, jack, shutter, mirror, primary, cleanup = rig
    mirror.fail_scan = True
    if failed_exit == "sc10":
        shutter.fail_exit = True
    else:
        jack.fail = True
    with pytest.raises(ValueError) as caught:
        anneal._run_laser_anneal_without_rotation_stage(config)
    assert caught.value is primary
    failures = getattr(primary, f"_{failed_exit}_cleanup_failures")
    assert len(failures) == 1
    assert failures[0] is cleanup
    assert events[-3:] == ["sc10 exit", "home", "labjack exit"]


def test_sc10_setup_failure_retains_existing_home_attempt_policy(rig):
    config, events, _, shutter, _, primary, _ = rig
    shutter.fail_setup = True
    with pytest.raises(ValueError) as caught:
        anneal._run_laser_anneal_without_rotation_stage(config)
    assert caught.value is primary
    assert events == ["home", "labjack exit"]


@pytest.mark.parametrize("scan_fails", [False, True])
def test_log_close_failure_does_not_replace_primary(rig, monkeypatch, scan_fails):
    config, events, _, _, mirror, primary, _ = rig
    mirror.fail_scan = scan_fails
    real_open = anneal.Path.open
    log_error = OSError("run log close failed")

    class Log:
        def write(self, text):
            return len(text)

        def flush(self):
            pass

        def close(self):
            events.append("log close")
            raise log_error

    def fake_open(path, *args, **kwargs):
        if path.name == "anneal_positions.csv":
            return Log()
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(anneal.Path, "open", fake_open)
    statuses = []
    with pytest.raises((ValueError, OSError)) as caught:
        anneal._run_laser_anneal_without_rotation_stage(
            replace(config, save_run_log=True), status_callback=statuses.append
        )
    assert caught.value is (primary if scan_fails else log_error)
    if scan_fails:
        assert any("close run log" in note for note in primary.__notes__)
    assert statuses[-1] == "Failed; cleanup commands attempted"
    assert events[-2:] == ["labjack exit", "log close"]


def test_outer_status_failure_cannot_prevent_stage_return(monkeypatch):
    events = []
    result = object()

    class Stage:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("exit")

        def move_to(self, coordinate):
            events.append(coordinate)

    def broken_status(message):
        raise RuntimeError("reporting failed")

    monkeypatch.setattr(anneal, "KinesisRotationStage", Stage)
    monkeypatch.setattr(anneal, "validate_run_config", lambda config: None)
    monkeypatch.setattr(
        anneal, "_run_laser_anneal_without_rotation_stage", lambda *a, **k: result
    )
    config = anneal.LaserAnnealConfig()
    assert anneal.run_laser_anneal(config, status_callback=broken_status) is result
    assert events == [config.anneal_rotation_coordinate, config.return_rotation_coordinate, "exit"]
