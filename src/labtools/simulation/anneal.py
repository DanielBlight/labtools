"""Synthetic anneal progress/state/logs, not a shutter or stage hardware model."""

import csv
import json
import math
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from threading import Event, Lock, get_ident

import numpy as np

from labtools.config.anneal_types import AnnealProgress, LaserAnnealResult


class SimulatedAnneal:
    """State scoped to one existing reservation authority; no native imports."""

    def __init__(self, require_owner, *, realtime=False):
        self._require_owner = require_owner
        self.realtime = realtime
        self._lock = Lock()
        self._state = {"synthetic": True, "shutter": "closed", "stage_coordinate": None,
                       "mirror_x_v": 0., "mirror_y_v": 0., "completed_points": 0,
                       "worker_thread": None, "running": False}

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def _update(self, **values):
        with self._lock:
            self._state.update(values)

    def run(self, config, *, stop_event=None, progress_callback=None, status_callback=None):
        config.validate()
        self._require_owner("Annealing")
        stop = stop_event if stop_event is not None else Event()
        started = time.monotonic()
        output = None
        completed = 0
        stopped = stop.is_set()
        thread = get_ident()
        self._update(running=True, completed_points=0, worker_thread=thread)
        handle = None
        writer = None
        error = None

        def status(text):
            if status_callback is not None:
                status_callback("SIMULATED: " + text)

        try:
            if config.save_run_log and not stopped:
                root = Path(config.output_root)
                root.mkdir(parents=True, exist_ok=True)
                output = Path(tempfile.mkdtemp(prefix="SIMULATED-anneal-", dir=root))
                data = asdict(config)
                data["output_root"] = str(data["output_root"])
                (output / "metadata.json").write_text(json.dumps({
                    "backend": "simulation", "synthetic": True,
                    "not_hardware_acceptance": True, "simulation_realtime": self.realtime, "config": data,
                    "model": "synthetic mirror grid, shutter state and stage coordinate; no thermal/dose model",
                }, indent=2), encoding="utf-8")
                handle = (output / "positions.csv").open("w", encoding="utf-8", newline="")
                writer = csv.writer(handle)
                writer.writerow(("backend", "sequence", "pass", "y_index", "x_index", "x_v", "y_v", "elapsed_s"))
            if not stopped:
                self._update(stage_coordinate=config.anneal_rotation_coordinate)
                status("stage at requested synthetic anneal coordinate")
                self._update(shutter="open")
                status("shutter open; scanning")
            xv = np.linspace(config.x_start_v, config.x_stop_v, config.x_points)
            yv = np.linspace(config.y_start_v, config.y_stop_v, config.y_points)
            last_emit = -math.inf
            for pass_index in range(config.passes):
                if stopped:
                    break
                for yi, y in enumerate(yv):
                    if stopped:
                        break
                    indices = range(config.x_points - 1, -1, -1) if config.serpentine and yi % 2 else range(config.x_points)
                    for xi in indices:
                        self._require_owner("Annealing")
                        if get_ident() != thread:
                            raise RuntimeError("Synthetic anneal changed operation thread")
                        if stop.is_set():
                            stopped = True
                            break
                        x = float(xv[xi])
                        self._update(mirror_x_v=x, mirror_y_v=float(y))
                        duration = config.point_dwell_s + config.mirror_settle_s
                        if self.realtime and stop.wait(duration):
                            stopped = True
                            break
                        completed += 1
                        self._update(completed_points=completed)
                        elapsed = time.monotonic() - started
                        if writer is not None:
                            writer.writerow(("simulation", completed, pass_index + 1, yi, xi, x, float(y), elapsed))
                        if progress_callback is not None and (elapsed - last_emit >= config.gui_update_interval_s
                                                              or completed == config.total_points):
                            progress_callback(AnnealProgress(completed, config.total_points, pass_index + 1,
                                                             config.passes, xi, yi, x, float(y), elapsed))
                            last_emit = elapsed
        except BaseException as exc:
            error = repr(exc)
            raise
        finally:
            # Synthetic cleanup must happen even if a callback or file write fails.
            self._update(shutter="closed", mirror_x_v=config.home_x_voltage_v,
                         mirror_y_v=config.home_y_voltage_v, running=False)
            if config.return_rotation_stage:
                self._update(stage_coordinate=config.return_rotation_coordinate)
            try:
                if handle is not None:
                    handle.close()
            finally:
                if output is not None:
                    (output / "result.json").write_text(json.dumps({
                        "backend": "simulation", "synthetic": True, "completed_points": completed,
                        "total_points": config.total_points, "stopped": stopped,
                        "error": error, "final_state": self.snapshot(),
                    }, indent=2), encoding="utf-8")
        status("stopped; synthetic cleanup complete" if stopped else "completed; synthetic cleanup complete")
        return LaserAnnealResult(not stopped and completed == config.total_points, stopped, completed,
                                 config.total_points, time.monotonic() - started, output)
