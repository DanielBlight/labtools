"""Multi-Z intensity maps with explicit coarse extensions, never DC above 60 V."""

import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from labtools.runtime.retained_results import export_retained
from labtools.runtime.sample_stage import StageStopped, finite


@dataclass(frozen=True)
class FocusPlan:
    voltages: tuple[float, ...]
    sweeps: int = 1
    steps_per_extension: int = 1
    direction: int = 1
    settle_s: float = .5

    def validate(self):
        if not self.voltages or len(self.voltages) > 200:
            raise ValueError("Enter between 1 and 200 DC levels")
        for value in self.voltages:
            finite(value, 0, 60, "Z DC level (V)")
        for name, value, low, high in (
            ("Sweeps", self.sweeps, 1, 50),
            ("Steps per extension", self.steps_per_extension, 1, 100),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{name} must be an integer from {low} to {high}")
        if self.direction not in (-1, 1) or isinstance(self.direction, bool):
            raise ValueError("Choose a signed coarse-step direction")
        finite(self.settle_s, 0, 30, "Z settling time (s)")
        if len(self.voltages) * self.sweeps > 1000:
            raise ValueError("A focus stack is limited to 1000 maps")
        return self


def empty_map(config):
    """An explicitly unmeasured result for Stop before the first map; no device calls."""
    from labtools.acquisition.intensity_map import IntensityMapResult

    shape = (config.y_points, config.x_points)
    return IntensityMapResult(
        x_values_v=np.linspace(config.x_start_v, config.x_stop_v, config.x_points),
        y_values_v=np.linspace(config.y_start_v, config.y_stop_v, config.y_points),
        channels=config.channels, counts=np.zeros((len(config.channels), *shape), dtype=np.int64),
        count_rates_cps=np.full((len(config.channels), *shape), np.nan),
        summed_count_rate_cps=np.full(shape, np.nan), completed_mask=np.zeros(shape, dtype=bool),
        timestamps_unix_s=np.full(shape, np.nan), session_ids=np.zeros(shape, dtype=np.int32),
        elapsed_s=0, output_directory=Path(config.output_root), complete=False, resumed=False,
    )


def run_focus_stack(stage, token, plan, config, acquisition, *, progress_callback=None,
                    cancel_requested=None, retain=None):
    """Called on the map worker while its optical lease and stage token are held.

    Leaves the last applied offset on completion, Stop or failure. No automatic
    return, coarse compensation, best-focus selection or image filtering.
    """
    plan.validate()
    config.validate()
    cancel_requested = cancel_requested or (lambda: False)
    def cancelled():
        return cancel_requested() or stage.stop_event.is_set()
    run = {"kind": "multi-z-intensity-map", "settings": config, "focus_plan": plan,
           "status": "running", "maps": [], "coarse_history": [], "active": None,
           "started_unix_s": time.time(), "simulated_stage": stage.simulated}
    if retain:
        retain(run)
    output = None
    if config.save_results:
        output = Path(config.output_root) / ("focus-stack-" + uuid.uuid4().hex[:12])
        output.mkdir(parents=True, exist_ok=False)
        run["output_directory"] = str(output)
    last = None
    primary = None
    try:
        stage.check_stop(cancelled)
        initial = stage.call(token, "read")
        if not initial["connected"]:
            raise RuntimeError("Connect the Stage popup before starting multiple Z focuses")
        run["initial_stage"] = initial
        for sweep in range(plan.sweeps):
            if sweep:
                for step in range(plan.steps_per_extension):
                    stage.check_stop(cancelled)
                    before = stage.call(token, "read")
                    # Every automatic coarse extension is one +Z step at 60 V.
                    stage.call(token, "amplitude", axis=1, value=60, cancel=cancelled)
                    after = stage.call(token, "step", axis=1, value=1, cancel=cancelled)
                    run["coarse_history"].append({"sweep": sweep, "step": step + 1,
                        "direction": plan.direction, "before": before, "after": after})
            for level, voltage in enumerate(plan.voltages):
                stage.check_stop(cancelled)
                state = stage.call(token, "ramp", axis=1, value=voltage, cancel=cancelled)
                stage.wait(plan.settle_s, cancelled)
                entry = {"sweep": sweep, "level": level, "requested_dc_v": voltage,
                         "stage_before": state, "latest_progress": None}
                run["active"] = entry
                index = len(run["maps"])
                def progress(snapshot, entry=entry):
                    entry["latest_progress"] = snapshot
                    if progress_callback:
                        progress_callback(snapshot)
                map_config = replace(config, output_root=output / f"map-{index + 1:04d}" if output else config.output_root)
                last = acquisition(map_config, resume_directory=None,
                                   progress_callback=progress, cancel_requested=cancelled)
                entry["result"] = last
                entry["stage_after"] = stage.call(token, "read")
                entry.pop("latest_progress", None)
                run["maps"].append(entry)
                run["active"] = None
                if retain:
                    retain(run)
                if cancelled() or not last.complete:
                    raise StageStopped("Focus stack stopped; partial maps retained")
        run["status"] = "completed"
    except StageStopped:
        run["status"] = "stopped"
    except BaseException as error:
        primary = error
        run["status"] = "failed"
        run["error"] = f"{type(error).__name__}: {error}"
        error.retained_focus_stack = run
        raise
    finally:
        run["finished_unix_s"] = time.time()
        if retain:
            retain(run)
        if output:
            try:
                export_retained(output, run, label="focus-stack", settings=config)
            except Exception as error:
                run["export_error"] = str(error)
                if primary is not None:
                    primary.add_note(f"Focus-stack export also failed: {error}")
                else:
                    raise
    return last, run
