"""Bounded ANC350 commands and multi-Z maps, using explicit fake hardware."""

from dataclasses import replace
from threading import get_ident

import numpy as np
import pytest

from labtools.acquisition.intensity_map import acquire_intensity_map
from labtools.config.intensity_map import IntensityMapConfig
from labtools.runtime.focus_stack import FocusPlan, empty_map, run_focus_stack
from labtools.runtime.retained_results import export_retained
from labtools.runtime.sample_stage import (
    AXES,
    SampleStage,
    SimulatedStage,
    StageStopped,
)


class TracedStage(SimulatedStage):
    def __init__(self):
        super().__init__()
        self.events = []
        self.thread = get_ident()
        self.limit = None
        self.fail_offset = False
        self.on_offset = None

    def set_offset(self, axis, voltage):
        assert get_ident() == self.thread
        assert 0 <= voltage <= 60
        self.events.append(("offset", axis, voltage))
        if self.fail_offset:
            raise OSError("USB write failed")
        super().set_offset(axis, voltage)
        if self.on_offset:
            self.on_offset()

    def move_by_steps(self, axis, steps):
        assert get_ident() == self.thread
        assert self.offset[axis] == 0
        self.events.append(("step", axis, steps))
        super().move_by_steps(axis, steps)

    def check_limit(self, axis):
        return self.limit

    def close(self):
        assert get_ident() == self.thread
        self.events.append(("close",))


@pytest.fixture
def rig():
    stage = SampleStage(simulated=True, factory=TracedStage, realtime=False)
    token = stage.claim()
    stage.call(token, "connect")
    yield stage, token
    stage.release(token)
    stage.shutdown()


@pytest.fixture
def config(tmp_path):
    return IntensityMapConfig(
        x_start_v=0, x_stop_v=1, x_points=2, y_start_v=0, y_stop_v=1, y_points=2,
        integration_time_s=.001, settle_time_s=0, channels=(2,),
        channel_thresholds_v=(.1,), channel_edges=("rising",), backend="simulation",
        simulation_realtime=False, save_results=False, output_root=tmp_path / "outputs",
    )


def acquire(config, **kwargs):
    return acquire_intensity_map(config, memory_only=not config.save_results, **kwargs)


def test_axes_and_connect_do_not_move(rig):
    stage, token = rig
    assert AXES == (("X", 0), ("Z", 1), ("Y", 2))
    assert stage.device.events == []
    assert stage.call(token, "read")["axes"]["Z"]["axis"] == 1
    assert stage.device.thread != get_ident()


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("target", [0, 15, 60])
def test_ramp_bounded_and_exact(rig, axis, target):
    stage, token = rig
    result = stage.call(token, "ramp", axis=axis, value=target)
    assert stage.device.offset[axis] == target
    assert result["connected"]
    writes = [e[2] for e in stage.device.events if e[0] == "offset"]
    assert len(writes) == (50 if target else 0)
    assert writes == sorted(writes)


@pytest.mark.parametrize("target", [-1, 61, float("nan"), float("inf"), True])
def test_invalid_dc_refused_before_write(rig, target):
    stage, token = rig
    with pytest.raises(ValueError):
        stage.call(token, "ramp", value=target)
    assert not stage.device.events


def test_step_ramps_zero_first_and_preserves_amplitude(rig):
    stage, token = rig
    stage.call(token, "ramp", value=60)
    stage.device.events.clear()
    stage.call(token, "step", value=-1)
    assert stage.device.events[-1] == ("step", 1, -1)
    assert stage.device.events[-2] == ("offset", 1, 0)
    assert stage.device.voltage[1] == 30


def test_stop_during_ramp_prevents_step(rig):
    stage, token = rig
    stage.call(token, "ramp", value=60)
    stage.device.events.clear()
    stage.device.on_offset = stage.request_stop
    with pytest.raises(StageStopped):
        stage.call(token, "step", value=1)
    assert not any(e[0] == "step" for e in stage.device.events)
    assert 0 < stage.device.offset[1] < 60


def test_limit_prevents_step(rig):
    stage, token = rig
    stage.device.limit = "fwd"
    with pytest.raises(RuntimeError, match="end of travel"):
        stage.call(token, "step", value=1)
    assert not any(e[0] == "step" for e in stage.device.events)


def test_exclusive_token_and_close_refusal(rig):
    stage, _token = rig
    with pytest.raises(RuntimeError):
        stage.claim()
    with pytest.raises(RuntimeError):
        stage.submit(object(), "read")
    with pytest.raises(RuntimeError):
        stage.shutdown()


def test_native_failure_never_falls_back():
    def fail():
        raise OSError("USB unavailable")
    stage = SampleStage(factory=fail)
    token = stage.claim()
    with pytest.raises(OSError):
        stage.call(token, "connect")
    assert not stage.connected
    stage.release(token)
    stage.shutdown()


def test_fault_blocks_further_movement(rig):
    stage, token = rig
    stage.device.fail_offset = True
    with pytest.raises(OSError):
        stage.call(token, "ramp", value=10)
    stage.device.fail_offset = False
    with pytest.raises(RuntimeError, match="fault"):
        stage.call(token, "ramp", value=10)


def test_stack_extensions_no_files_then_save(rig, config, tmp_path):
    stage, token = rig
    last, run = run_focus_stack(stage, token, FocusPlan((0, 30, 60), sweeps=2, settle_s=0), config, acquire)
    assert last.complete and run["status"] == "completed"
    assert len(run["maps"]) == 6 and len(run["coarse_history"]) == 1
    assert stage.device.offset[1] == 60
    assert not config.output_root.exists()
    target = export_retained(tmp_path / "saved", run, label="focus-stack")
    assert (target / "arrays.npz").exists()
    with np.load(target / "arrays.npz", allow_pickle=False) as arrays:
        assert len(arrays.files) > 6


def test_stack_stop_retains_first_map_no_later_steps(rig, config):
    stage, token = rig
    def stopped_acquire(config, **kwargs):
        result = acquire(config, **kwargs)
        stage.request_stop()
        return result
    _last, run = run_focus_stack(stage, token, FocusPlan((0, 60), sweeps=2), config, stopped_acquire)
    assert run["status"] == "stopped" and len(run["maps"]) == 1
    assert not run["coarse_history"]


def test_stack_failure_retains_completed_maps_and_progress(rig, config):
    stage, token = rig
    calls = []
    def failure(config, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            kwargs["progress_callback"]("partial progress")
            raise OSError("count failed")
        return acquire(config, **kwargs)
    with pytest.raises(OSError) as caught:
        run_focus_stack(stage, token, FocusPlan((0, 30), settle_s=0), config, failure)
    run = caught.value.retained_focus_stack
    assert len(run["maps"]) == 1
    assert run["active"]["latest_progress"] == "partial progress"
    assert run["status"] == "failed"


def test_automatic_output(rig, config):
    stage, token = rig
    _last, run = run_focus_stack(stage, token, FocusPlan((0,), settle_s=0), replace(config, save_results=True), acquire)
    assert run["output_directory"]
    assert list(config.output_root.rglob("intensity_map_complete.npz"))
    assert list(config.output_root.rglob("run.json"))


@pytest.mark.parametrize("plan", [FocusPlan(()), FocusPlan((61,)), FocusPlan((0,), sweeps=0),
    FocusPlan((0,), steps_per_extension=0), FocusPlan((0,), direction=0),
    FocusPlan((0,), settle_s=-1), FocusPlan((0,), settle_s=float("nan"))])
def test_invalid_plans(plan):
    with pytest.raises(ValueError):
        plan.validate()


def test_empty_map_has_no_measured_pixels(config):
    result = empty_map(config)
    assert not result.complete and not result.completed_mask.any()
    assert np.isnan(result.summed_count_rate_cps).all()


def test_stop_before_first_map_no_motion_or_files(rig, config):
    stage, token = rig
    stage.request_stop()
    last, run = run_focus_stack(stage, token, FocusPlan((0, 60)), config, acquire)
    assert last is None and run["status"] == "stopped"
    assert not run["maps"] and not stage.device.events
    assert not config.output_root.exists()


def test_disable_ramps_zero_before_grounding(rig):
    stage, token = rig
    stage.call(token, "ramp", value=30)
    stage.call(token, "enable", value=False)
    assert stage.device.offset[1] == 0
    assert not stage.device.enabled[1]


def test_focus_preferences_validate():
    from labtools.runtime.unified_inputs import validate_display
    data = {"focus_enabled": True, "focus_levels": "0, 20, 60", "focus_sweeps": 2,
            "focus_steps": 1, "focus_direction": 1, "focus_settle": .5}
    assert validate_display(data) == data
    with pytest.raises(ValueError):
        validate_display({**data, "focus_levels": "0, 70"})


def test_ramp_wait_budget_is_half_second(rig):
    stage, token = rig
    waits = []
    stage.wait = lambda seconds, cancel=None: waits.append(seconds)
    stage.call(token, "ramp", value=60)
    assert sum(waits) == pytest.approx(.5)


def test_stage_lifecycle_helper_recognises_stage():
    from types import SimpleNamespace

    from labtools.simulation.workspace import busy_workflows, stop_workflows
    calls = []
    page = SimpleNamespace(busy=True, request_stop=lambda: calls.append(True))
    assert busy_workflows({"Stage": page}) == ("Stage",)
    assert stop_workflows({"Stage": page}) == ()
    assert calls == [True]


def test_enable_starts_at_zero_then_ramps_stored_offset(rig):
    stage, token = rig
    stage.device.offset[1] = 30
    stage.device.enabled[1] = False
    stage.call(token, "enable", value=True)
    writes = [e[2] for e in stage.device.events if e[0] == "offset"]
    assert writes[0] == 0 and writes[-1] == 30
    assert len(writes) == 51
    assert stage.device.enabled[1]
