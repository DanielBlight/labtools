"""Offline lifecycle characterization for the laser-anneal acquisition."""

from labtools.acquisition import laser_anneal


class StopDuringFirstDwell:
    def __init__(self):
        self.wait_calls = 0

    def is_set(self):
        return False

    def wait(self, _timeout):
        self.wait_calls += 1
        return self.wait_calls == 3


class FakeLabJack:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class FakeMirror:
    instance = None

    def __init__(self, _labjack, *, dio_pin):
        self.dio_pin = dio_pin
        self.moves = []
        type(self).instance = self

    def move(self, x_voltage, y_voltage):
        self.moves.append((x_voltage, y_voltage))


class FakeShutter:
    instance = None

    def __init__(self, **_kwargs):
        self.enabled = []
        self.mode = None
        type(self).instance = self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def set_mode(self, mode):
        self.mode = mode

    def set_enabled(self, enabled):
        self.enabled.append(enabled)


def test_cancellation_closes_shutter_and_returns_mirror_home(monkeypatch, tmp_path):
    monkeypatch.setattr(laser_anneal, "LabJackU6", FakeLabJack)
    monkeypatch.setattr(laser_anneal, "ScanningMirror", FakeMirror)
    monkeypatch.setattr(laser_anneal, "SC10", FakeShutter)

    config = laser_anneal.LaserAnnealConfig(
        x_start_v=-1.0,
        x_stop_v=1.0,
        x_points=2,
        y_start_v=2.0,
        y_stop_v=2.0,
        y_points=1,
        point_dwell_s=1.0,
        mirror_settle_s=1.0,
        home_x_voltage_v=0.25,
        home_y_voltage_v=-0.5,
        output_root=tmp_path,
        save_run_log=False,
    )

    result = laser_anneal._run_laser_anneal_without_rotation_stage(
        config, stop_event=StopDuringFirstDwell()
    )

    assert result.stopped is True
    assert result.completed is False
    assert result.completed_points == 0
    assert FakeShutter.instance.mode == laser_anneal.SC10Mode.MANUAL
    assert FakeShutter.instance.enabled == [False, True, False]
    assert FakeMirror.instance.moves[-1] == (0.25, -0.5)
