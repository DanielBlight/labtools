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

class FakeRotationStage:
    instance = None

    def __init__(self, *, move_timeout_s):
        self.move_timeout_s = move_timeout_s
        self.moves = []
        type(self).instance = self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def move_to(self, coordinate):
        self.moves.append(coordinate)


def test_rotation_stage_returns_after_inner_anneal_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(laser_anneal, "SC10", FakeShutter)
    monkeypatch.setattr(laser_anneal, "KinesisRotationStage", FakeRotationStage)

    def fail_inner(*_args, **_kwargs):
        raise RuntimeError("inner anneal failed")

    monkeypatch.setattr(
        laser_anneal, "_run_laser_anneal_without_rotation_stage", fail_inner
    )
    monkeypatch.setattr(laser_anneal, "validate_run_config", lambda _config: None)

    config = laser_anneal.LaserAnnealConfig(
        anneal_rotation_coordinate=35_000.0,
        return_rotation_coordinate=90_000.0,
        return_rotation_stage=True,
        rotation_stage_timeout_s=12.5,
        output_root=tmp_path,
        save_run_log=False,
    )

    try:
        laser_anneal.run_laser_anneal(config)
    except RuntimeError as error:
        assert str(error) == "inner anneal failed"
    else:
        raise AssertionError("expected inner anneal failure")

    assert FakeRotationStage.instance.move_timeout_s == 12.5
    assert FakeRotationStage.instance.moves == [35_000.0, 90_000.0]

class FailingReturnRotationStage(FakeRotationStage):
    def move_to(self, coordinate):
        self.moves.append(coordinate)
        if len(self.moves) == 2:
            raise RuntimeError("stage return failed")


def test_inner_failure_is_preserved_when_stage_return_also_fails(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(laser_anneal, "SC10", FakeShutter)
    monkeypatch.setattr(
        laser_anneal, "KinesisRotationStage", FailingReturnRotationStage
    )

    def fail_inner(*_args, **_kwargs):
        raise ValueError("inner anneal failed")

    monkeypatch.setattr(
        laser_anneal, "_run_laser_anneal_without_rotation_stage", fail_inner
    )
    monkeypatch.setattr(laser_anneal, "validate_run_config", lambda _config: None)

    config = laser_anneal.LaserAnnealConfig(
        anneal_rotation_coordinate=35_000.0,
        return_rotation_coordinate=90_000.0,
        return_rotation_stage=True,
        output_root=tmp_path,
        save_run_log=False,
    )

    try:
        laser_anneal.run_laser_anneal(config)
    except ValueError as error:
        assert str(error) == "inner anneal failed"
        assert error.__notes__ == [
            "Cleanup failed (return rotation stage): RuntimeError('stage return failed')"
        ]
    else:
        raise AssertionError("expected inner anneal failure")

    assert FailingReturnRotationStage.instance.moves == [35_000.0, 90_000.0]


def test_stage_return_only_failure_raises_cleanup_group(monkeypatch, tmp_path):
    monkeypatch.setattr(laser_anneal, "SC10", FakeShutter)
    monkeypatch.setattr(
        laser_anneal, "KinesisRotationStage", FailingReturnRotationStage
    )
    monkeypatch.setattr(
        laser_anneal,
        "_run_laser_anneal_without_rotation_stage",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(laser_anneal, "validate_run_config", lambda _config: None)

    config = laser_anneal.LaserAnnealConfig(
        anneal_rotation_coordinate=35_000.0,
        return_rotation_coordinate=90_000.0,
        return_rotation_stage=True,
        output_root=tmp_path,
        save_run_log=False,
    )

    try:
        laser_anneal.run_laser_anneal(config)
    except ExceptionGroup as group:
        assert str(group) == "Acquisition cleanup failed (1 sub-exception)"
        assert len(group.exceptions) == 1
        failure = group.exceptions[0]
        assert isinstance(failure, RuntimeError)
        assert str(failure) == "stage return failed"
        assert failure.__notes__ == ["Cleanup action: return rotation stage"]
    else:
        raise AssertionError("expected cleanup failure group")

    assert FailingReturnRotationStage.instance.moves == [35_000.0, 90_000.0]

class FailingScanAndHomeMirror(FakeMirror):
    def move(self, x_voltage, y_voltage):
        self.moves.append((x_voltage, y_voltage))
        if len(self.moves) == 2:
            raise ValueError("scan move failed")
        if len(self.moves) == 3:
            raise RuntimeError("mirror home failed")


class FailingCloseShutter(FakeShutter):
    def set_enabled(self, enabled):
        self.enabled.append(enabled)
        if self.enabled == [False, True, False]:
            raise RuntimeError("shutter close failed")


def test_scan_failure_is_preserved_when_shutter_close_and_mirror_home_fail(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(laser_anneal, "LabJackU6", FakeLabJack)
    monkeypatch.setattr(laser_anneal, "ScanningMirror", FailingScanAndHomeMirror)
    monkeypatch.setattr(laser_anneal, "SC10", FailingCloseShutter)

    config = laser_anneal.LaserAnnealConfig(
        x_start_v=-1.0,
        x_stop_v=1.0,
        x_points=2,
        y_start_v=2.0,
        y_stop_v=2.0,
        y_points=1,
        point_dwell_s=0.0,
        mirror_settle_s=0.0,
        home_x_voltage_v=0.25,
        home_y_voltage_v=-0.5,
        output_root=tmp_path,
        save_run_log=False,
    )

    try:
        laser_anneal._run_laser_anneal_without_rotation_stage(config)
    except ValueError as error:
        assert str(error) == "scan move failed"
        assert error.__notes__ == [
            "Cleanup failed (close shutter): RuntimeError('shutter close failed')",
            "Cleanup failed (return mirror home): RuntimeError('mirror home failed')",
        ]
    else:
        raise AssertionError("expected scan move failure")

    assert FailingCloseShutter.instance.enabled == [False, True, False]
    assert FailingScanAndHomeMirror.instance.moves[-1] == (0.25, -0.5)

class CleanupOnlyMirror(FakeMirror):
    fail_home = False

    def move(self, x_voltage, y_voltage):
        self.moves.append((x_voltage, y_voltage))
        if self.fail_home and len(self.moves) == 4:
            raise RuntimeError("mirror home failed")


class CleanupOnlyShutter(FakeShutter):
    fail_close = False

    def set_enabled(self, enabled):
        self.enabled.append(enabled)
        if self.fail_close and self.enabled == [False, True, False]:
            raise RuntimeError("shutter close failed")


def run_successful_scan_with_cleanup_failures(
    monkeypatch, tmp_path, *, fail_close, fail_home
):
    CleanupOnlyMirror.fail_home = fail_home
    CleanupOnlyShutter.fail_close = fail_close
    monkeypatch.setattr(laser_anneal, "LabJackU6", FakeLabJack)
    monkeypatch.setattr(laser_anneal, "ScanningMirror", CleanupOnlyMirror)
    monkeypatch.setattr(laser_anneal, "SC10", CleanupOnlyShutter)

    config = laser_anneal.LaserAnnealConfig(
        x_start_v=-1.0,
        x_stop_v=1.0,
        x_points=2,
        y_start_v=2.0,
        y_stop_v=2.0,
        y_points=1,
        point_dwell_s=0.0,
        mirror_settle_s=0.0,
        home_x_voltage_v=0.25,
        home_y_voltage_v=-0.5,
        output_root=tmp_path,
        save_run_log=False,
    )
    return laser_anneal._run_laser_anneal_without_rotation_stage(config)


def cleanup_failures(group):
    assert str(group) == "Acquisition cleanup failed (1 sub-exception)"
    inner = group.exceptions[0]
    if isinstance(inner, ExceptionGroup):
        return list(inner.exceptions)
    return [inner]


def test_shutter_close_only_failure_raises_cleanup_group(monkeypatch, tmp_path):
    try:
        run_successful_scan_with_cleanup_failures(
            monkeypatch, tmp_path, fail_close=True, fail_home=False
        )
    except ExceptionGroup as group:
        failures = cleanup_failures(group)
        assert [str(error) for error in failures] == ["shutter close failed"]
        assert failures[0].__notes__ == ["Cleanup action: close shutter"]
    else:
        raise AssertionError("expected cleanup failure group")

    assert CleanupOnlyShutter.instance.enabled == [False, True, False]
    assert CleanupOnlyMirror.instance.moves[-1] == (0.25, -0.5)


def test_mirror_home_only_failure_raises_cleanup_group(monkeypatch, tmp_path):
    try:
        run_successful_scan_with_cleanup_failures(
            monkeypatch, tmp_path, fail_close=False, fail_home=True
        )
    except ExceptionGroup as group:
        failures = cleanup_failures(group)
        assert [str(error) for error in failures] == ["mirror home failed"]
        assert failures[0].__notes__ == ["Cleanup action: return mirror home"]
    else:
        raise AssertionError("expected cleanup failure group")

    assert CleanupOnlyShutter.instance.enabled == [False, True, False]
    assert CleanupOnlyMirror.instance.moves[-1] == (0.25, -0.5)


def test_both_inner_cleanup_failures_are_reported(monkeypatch, tmp_path):
    try:
        run_successful_scan_with_cleanup_failures(
            monkeypatch, tmp_path, fail_close=True, fail_home=True
        )
    except ExceptionGroup as group:
        assert str(group) == "Acquisition cleanup failed (1 sub-exception)"
        assert len(group.exceptions) == 1

        assert group.__notes__ == [
            "Cleanup failed (return mirror home): RuntimeError('mirror home failed')"
        ]

        shutter_failure = group.exceptions[0]
        assert isinstance(shutter_failure, RuntimeError)
        assert str(shutter_failure) == "shutter close failed"
        assert shutter_failure.__notes__ == ["Cleanup action: close shutter"]
    else:
        raise AssertionError("expected cleanup failure group")

    assert CleanupOnlyShutter.instance.enabled == [False, True, False]
    assert CleanupOnlyMirror.instance.moves[-1] == (0.25, -0.5)

class FailingCloseAndExitShutter(CleanupOnlyShutter):
    fail_close = True
    __exit__ = laser_anneal.SC10.__exit__

    def close(self):
        raise RuntimeError("SC10 context exit failed")


def test_sc10_exit_failure_preserves_shutter_cleanup_group_and_mirror_home(
    monkeypatch, tmp_path
):
    CleanupOnlyMirror.fail_home = False
    monkeypatch.setattr(laser_anneal, "LabJackU6", FakeLabJack)
    monkeypatch.setattr(laser_anneal, "ScanningMirror", CleanupOnlyMirror)
    monkeypatch.setattr(laser_anneal, "SC10", FailingCloseAndExitShutter)

    config = laser_anneal.LaserAnnealConfig(
        x_start_v=-1.0,
        x_stop_v=1.0,
        x_points=2,
        y_start_v=2.0,
        y_stop_v=2.0,
        y_points=1,
        point_dwell_s=0.0,
        mirror_settle_s=0.0,
        home_x_voltage_v=0.25,
        home_y_voltage_v=-0.5,
        output_root=tmp_path,
        save_run_log=False,
    )

    try:
        laser_anneal._run_laser_anneal_without_rotation_stage(config)
    except ExceptionGroup as group:
        assert str(group) == "Acquisition cleanup failed (1 sub-exception)"
        assert group.__notes__ == [
            "SC10 cleanup also failed: RuntimeError('SC10 context exit failed')"
        ]
        assert len(group.exceptions) == 1
        shutter_failure = group.exceptions[0]
        assert isinstance(shutter_failure, RuntimeError)
        assert str(shutter_failure) == "shutter close failed"
        assert shutter_failure.__notes__ == ["Cleanup action: close shutter"]
        assert len(group._sc10_cleanup_failures) == 1
        assert isinstance(group._sc10_cleanup_failures[0], RuntimeError)
        assert str(group._sc10_cleanup_failures[0]) == "SC10 context exit failed"
    else:
        raise AssertionError("expected shutter cleanup failure group")

    assert FailingCloseAndExitShutter.instance.enabled == [False, True, False]
    assert CleanupOnlyMirror.instance.moves[-1] == (0.25, -0.5)

class FailingExitLabJack(FakeLabJack):
    __exit__ = laser_anneal.LabJackU6.__exit__

    def close(self):
        raise OSError("LabJack close failed")


def test_labjack_exit_preserves_mirror_home_failure(monkeypatch, tmp_path):
    CleanupOnlyMirror.fail_home = True
    CleanupOnlyShutter.fail_close = False
    monkeypatch.setattr(laser_anneal, "LabJackU6", FailingExitLabJack)
    monkeypatch.setattr(laser_anneal, "ScanningMirror", CleanupOnlyMirror)
    monkeypatch.setattr(laser_anneal, "SC10", CleanupOnlyShutter)

    config = laser_anneal.LaserAnnealConfig(
        x_start_v=-1.0,
        x_stop_v=1.0,
        x_points=2,
        y_start_v=2.0,
        y_stop_v=2.0,
        y_points=1,
        point_dwell_s=0.0,
        mirror_settle_s=0.0,
        home_x_voltage_v=0.25,
        home_y_voltage_v=-0.5,
        output_root=tmp_path,
        save_run_log=False,
    )

    try:
        laser_anneal._run_laser_anneal_without_rotation_stage(config)
    except ExceptionGroup as group:
        assert str(group) == "Acquisition cleanup failed (1 sub-exception)"
        assert group.__notes__ == [
            "LabJack cleanup also failed: OSError('LabJack close failed')"
        ]
        failure = group.exceptions[0]
        assert isinstance(failure, RuntimeError)
        assert str(failure) == "mirror home failed"
        assert failure.__notes__ == ["Cleanup action: return mirror home"]
        assert str(group._labjack_cleanup_failures[0]) == "LabJack close failed"
    else:
        raise AssertionError("expected mirror-home cleanup failure group")

    assert CleanupOnlyShutter.instance.enabled == [False, True, False]
    assert CleanupOnlyMirror.instance.moves[-1] == (0.25, -0.5)
