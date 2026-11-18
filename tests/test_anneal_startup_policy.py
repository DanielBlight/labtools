"""Public-entry startup ordering and maintainer-selected cleanup policy."""

from dataclasses import replace

import pytest

from labtools.acquisition import laser_anneal as anneal


@pytest.fixture
def startup_rig(monkeypatch, tmp_path):
    events = []
    state = {"fail": None, "closes": 0}
    setup_error = OSError("shutter setup failed")
    scan_error = ValueError("scan failed")
    close_error = RuntimeError("shutter close failed")

    class Shutter:
        def __init__(self, **kwargs):
            events.append("shutter connect")
            if state["fail"] == "connect":
                raise setup_error

        def __enter__(self):
            events.append("shutter enter")
            if state["fail"] == "enter":
                raise setup_error
            return self

        def __exit__(self, *args):
            events.append("shutter exit")

        def set_mode(self, mode):
            events.append("manual")
            if state["fail"] == "mode":
                raise setup_error

        def set_enabled(self, enabled):
            events.append("open" if enabled else "close")
            if not enabled:
                state["closes"] += 1
                if state["fail"] == "initial close" and state["closes"] == 1:
                    raise setup_error
                if state["fail"] in {"cleanup close", "scan and close"} and state["closes"] == 2:
                    raise close_error

    class Stage:
        def __init__(self, **kwargs):
            events.append("stage connect")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("stage exit")

        def move_to(self, coordinate):
            events.append("stage anneal" if coordinate == 35000 else "stage return")

    class Jack:
        def __init__(self):
            events.append("labjack connect")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("labjack exit")

    class Mirror:
        def __init__(self, *args, **kwargs):
            events.append("mirror construct")
            self.moves = 0

        def move(self, x, y):
            self.moves += 1
            if (x, y) == (0.25, -0.5):
                events.append("home")
            else:
                events.append("scan move")
                if self.moves == 2 and state["fail"] == "scan and close":
                    raise scan_error

    monkeypatch.setattr(anneal, "SC10", Shutter)
    monkeypatch.setattr(anneal, "KinesisRotationStage", Stage)
    monkeypatch.setattr(anneal, "LabJackU6", Jack)
    monkeypatch.setattr(anneal, "ScanningMirror", Mirror)
    monkeypatch.setattr(anneal, "validate_run_config", lambda config: None)
    config = anneal.LaserAnnealConfig(
        x_points=1, y_points=1, point_dwell_s=0, mirror_settle_s=0,
        home_x_voltage_v=0.25, home_y_voltage_v=-0.5,
        output_root=tmp_path, save_run_log=False,
    )
    return config, events, state, setup_error, scan_error


@pytest.mark.parametrize("phase", ["connect", "enter", "mode", "initial close"])
def test_shutter_startup_failure_causes_no_motion_or_motion_connections(startup_rig, phase):
    config, events, state, error, _ = startup_rig
    state["fail"] = phase
    with pytest.raises(OSError) as caught:
        anneal.run_laser_anneal(config)
    assert caught.value is error
    assert not any(event.startswith(("stage", "labjack", "mirror")) for event in events)
    assert "home" not in events
    if phase in {"mode", "initial close"}:
        assert events[-1] == "shutter exit"


def test_same_ready_shutter_connection_is_reused_for_scan(startup_rig):
    config, events, _, _, _ = startup_rig
    assert anneal.run_laser_anneal(config).completed
    assert events == [
        "shutter connect", "shutter enter", "manual", "close",
        "stage connect", "stage anneal", "labjack connect", "mirror construct",
        "scan move", "open", "scan move", "close", "home", "labjack exit",
        "stage return", "stage exit", "shutter exit",
    ]


@pytest.mark.parametrize("phase", ["cleanup close", "scan and close"])
def test_close_failure_still_homes_and_returns_stage(startup_rig, phase):
    config, events, state, _, primary = startup_rig
    state["fail"] = phase
    with pytest.raises((ExceptionGroup, ValueError)) as caught:
        anneal.run_laser_anneal(config)
    if phase == "scan and close":
        assert caught.value is primary
        assert any("close shutter" in note for note in primary.__notes__)
    else:
        assert isinstance(caught.value, ExceptionGroup)
        assert str(caught.value.exceptions[0]) == "shutter close failed"
    assert events[-6:] == ["close", "home", "labjack exit", "stage return", "stage exit", "shutter exit"]


def test_disabled_stage_return_is_respected(startup_rig):
    config, events, _, _, _ = startup_rig
    assert anneal.run_laser_anneal(replace(config, return_rotation_stage=False)).completed
    assert "home" in events
    assert "stage return" not in events
