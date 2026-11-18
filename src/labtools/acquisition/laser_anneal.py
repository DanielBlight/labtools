"""Interruptible no-pause scanning-mirror laser anneal."""

from __future__ import annotations

import csv
import json
import sys
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import numpy as np
from loguru import logger

# labtools operator workspace v1
from labtools.config.anneal_workspace import validate_run_config
from labtools.devices.kinesis_rotation_stage import KinesisRotationStage
from labtools.devices.labjack_u6 import LabJackU6
from labtools.devices.sc10 import SC10, SC10Mode
from labtools.devices.scanning_mirror import ScanningMirror
from labtools.runtime.cleanup import cleanup_actions

ProgressCallback = Callable[["AnnealProgress"], None]
StatusCallback = Callable[[str], None]


@dataclass(frozen=True)
class LaserAnnealConfig:
    instrument_profile_id: str = ""
    instrument_profile_sha256: str = ""
    software_version: str = ""
    x_start_v: float = -1.0
    x_stop_v: float = 1.0
    x_points: int = 2
    y_start_v: float = 1.0
    y_stop_v: float = 3.0
    y_points: int = 2
    passes: int = 1
    point_dwell_s: float = 0.001
    mirror_settle_s: float = 0.0
    serpentine: bool = False
    minimum_mirror_voltage_v: float = -5.0
    maximum_mirror_voltage_v: float = 5.0
    mirror_dio_pin: int = 2
    home_x_voltage_v: float = 0.0
    home_y_voltage_v: float = 0.0
    sc10_port: str = "COM4"
    sc10_baud_rate: int = 9600
    sc10_timeout_s: float = 0.5
    anneal_rotation_coordinate: float = 35000.0
    return_rotation_coordinate: float = 90000.0
    return_rotation_stage: bool = True
    rotation_stage_timeout_s: float = 60.0
    output_root: Path = Path("C:/LabData/LaserAnneal")
    save_run_log: bool = True
    maximum_open_time_s: float = 900.0
    gui_update_interval_s: float = 0.05

    def validate(self) -> None:
        if min(self.x_points, self.y_points, self.passes) < 1:
            raise ValueError("Point counts and passes must be at least one")
        if min(self.point_dwell_s, self.mirror_settle_s) < 0:
            raise ValueError("Dwell and settle times cannot be negative")
        if not self.sc10_port.strip():
            raise ValueError("An SC10 COM port is required")
        if self.rotation_stage_timeout_s <= 0:
            raise ValueError("Rotation-stage timeout must be greater than zero")
        for name, value in (
            ("x_start_v", self.x_start_v),
            ("x_stop_v", self.x_stop_v),
            ("y_start_v", self.y_start_v),
            ("y_stop_v", self.y_stop_v),
            ("home_x_voltage_v", self.home_x_voltage_v),
            ("home_y_voltage_v", self.home_y_voltage_v),
        ):
            if (
                not self.minimum_mirror_voltage_v
                <= value
                <= self.maximum_mirror_voltage_v
            ):
                raise ValueError(
                    f"{name}={value} V is outside the configured mirror limits"
                )
        if self.estimated_open_time_s > self.maximum_open_time_s:
            raise ValueError(
                f"Estimated open time {self.estimated_open_time_s:.1f} s exceeds maximum {self.maximum_open_time_s:.1f} s"
            )

    @property
    def total_points(self) -> int:
        return self.x_points * self.y_points * self.passes

    @property
    def estimated_open_time_s(self) -> float:
        return self.total_points * (self.point_dwell_s + self.mirror_settle_s)


@dataclass(frozen=True)
class AnnealProgress:
    sequence: int
    total_points: int
    pass_index: int
    passes: int
    x_index: int
    y_index: int
    x_voltage_v: float
    y_voltage_v: float
    elapsed_s: float


@dataclass(frozen=True)
class LaserAnnealResult:
    completed: bool
    stopped: bool
    completed_points: int
    total_points: int
    elapsed_s: float
    output_directory: Path | None


def _indices(c):
    for p in range(c.passes):
        for yi in range(c.y_points):
            xs = (
                range(c.x_points - 1, -1, -1)
                if c.serpentine and yi % 2
                else range(c.x_points)
            )
            for xi in xs:
                yield p, yi, xi


def _new_dir(root: Path) -> Path:
    """Atomically allocate a timestamped directory without reusing a prior run."""
    root = Path(root)
    stem = datetime.now(UTC).astimezone().strftime("%Y-%m-%d_%H-%M-%S")
    root.mkdir(parents=True, exist_ok=True)
    for index in range(10_000):
        suffix = "" if index == 0 else f"-{index:03d}"
        path = root / f"{stem}{suffix}"
        try:
            path.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        return path
    raise RuntimeError(f"Could not allocate a unique output directory under {root}")


def _run_laser_anneal_without_rotation_stage(
    config: LaserAnnealConfig,
    *,
    stop_event: Event | None = None,
    progress_callback: ProgressCallback | None = None,
    status_callback: StatusCallback | None = None,
    _prepared_shutter: SC10 | None = None,
) -> LaserAnnealResult:
    """Run an anneal; stop requests interrupt dwell and are checked during setup."""
    config.validate()
    stop = stop_event or Event()
    reporting_failures: list[Exception] = []

    def status(message: str) -> None:
        if status_callback is None:
            return
        try:
            status_callback(message)
        except Exception as error:  # noqa: BLE001 - reporting must not prevent cleanup
            reporting_failures.append(error)

    xv = np.linspace(config.x_start_v, config.x_stop_v, config.x_points)
    yv = np.linspace(config.y_start_v, config.y_stop_v, config.y_points)
    out = _new_dir(config.output_root) if config.save_run_log else None
    started = time.monotonic()
    completed = 0
    stopped = False
    handle = None
    writer = None
    shutter_open = False
    if out:
        (out / "metadata.json").write_text(
            json.dumps(
                {
                    "started_at": datetime.now(UTC)
                    .astimezone()
                    .isoformat(timespec="seconds"),
                    "config": {
                        **asdict(config),
                        "output_root": str(config.output_root),
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        handle = (out / "anneal_positions.csv").open("w", newline="", encoding="utf-8")
        writer = csv.writer(handle)
        writer.writerow(
            (
                "sequence",
                "pass",
                "y_index",
                "x_index",
                "x_voltage_v",
                "y_voltage_v",
                "elapsed_s",
            )
        )
    try:
        status("Connecting to LabJack")
        with LabJackU6() as labjack:
            if stop.is_set():
                stopped = True
            status("Initialising scanning mirror")
            mirror = ScanningMirror(labjack, dio_pin=config.mirror_dio_pin)
            status("Connecting to SC10")
            def return_mirror_home() -> None:
                status("Returning mirror home")
                mirror.move(config.home_x_voltage_v, config.home_y_voltage_v)

            with (
                cleanup_actions(("return mirror home", return_mirror_home)),
                (
                    SC10(
                        port=config.sc10_port,
                        baud_rate=config.sc10_baud_rate,
                        timeout_s=config.sc10_timeout_s,
                    )
                    if _prepared_shutter is None
                    else nullcontext(_prepared_shutter)
                ) as shutter,
            ):
                def close_shutter() -> None:
                    nonlocal shutter_open
                    status("Closing shutter")
                    shutter.set_enabled(False)
                    shutter_open = False

                with cleanup_actions(("close shutter", close_shutter)):
                    if _prepared_shutter is None:
                        shutter_open = True  # unknown until a close command succeeds
                        shutter.set_mode(SC10Mode.MANUAL)
                        shutter.set_enabled(False)
                    shutter_open = False
                    status("Moving mirror to first point")
                    first = next(_indices(config))
                    _, fy, fx = first
                    mirror.move(float(xv[fx]), float(yv[fy]))
                    if stop.wait(config.mirror_settle_s):
                        stopped = True
                    if not stopped:
                        status("Opening shutter")
                        # A failed enable command may still have reached the device.
                        shutter_open = True
                        shutter.set_enabled(True)
                        status("Shutter open; scanning")
                        last_emit = 0.0
                        for p, yi, xi in _indices(config):
                            if stop.is_set():
                                stopped = True
                                break
                            x = float(xv[xi])
                            y = float(yv[yi])
                            mirror.move(x, y)
                            if stop.wait(config.mirror_settle_s):
                                stopped = True
                                break
                            if stop.wait(config.point_dwell_s):
                                stopped = True
                                break
                            completed += 1
                            elapsed = time.monotonic() - started
                            update = AnnealProgress(
                                completed,
                                config.total_points,
                                p + 1,
                                config.passes,
                                xi,
                                yi,
                                x,
                                y,
                                elapsed,
                            )
                            if writer:
                                writer.writerow(
                                    (completed, p + 1, yi, xi, x, y, elapsed)
                                )
                                handle.flush()
                            now = time.monotonic()
                            if progress_callback and (
                                now - last_emit >= config.gui_update_interval_s
                                or completed == config.total_points
                            ):
                                progress_callback(update)
                                last_emit = now
    except Exception:
        logger.exception("Laser anneal failed")
        raise
    finally:
        primary = sys.exception()
        log_close_failed = False
        try:
            if handle:
                handle.close()
        except Exception as error:
            log_close_failed = True
            if primary is None:
                raise
            primary.add_note(f"Cleanup failed (close run log): {error!r}")
        finally:
            if shutter_open:
                status("Cleanup incomplete: shutter state uncertain")
            elif primary is not None or log_close_failed:
                status("Failed; cleanup commands attempted")
            else:
                status("Finished")
            if primary is not None:
                for error in reporting_failures:
                    primary.add_note(f"Status callback failed: {error!r}")
            elif reporting_failures:
                logger.warning(
                    "Anneal status callback failed {} time(s): {!r}",
                    len(reporting_failures),
                    reporting_failures[-1],
                )
    elapsed = time.monotonic() - started
    return LaserAnnealResult(
        completed == config.total_points,
        stopped,
        completed,
        config.total_points,
        elapsed,
        out,
    )


def run_laser_anneal(
    config: LaserAnnealConfig,
    *,
    stop_event: Event | None = None,
    progress_callback: ProgressCallback | None = None,
    status_callback: StatusCallback | None = None,
) -> LaserAnnealResult:
    """Select anneal power, run the scan, then optionally return the stage."""
    validate_run_config(config)
    config.validate()
    def status(message: str) -> None:
        if status_callback is None:
            return
        try:
            status_callback(message)
        except Exception as error:  # noqa: BLE001 - reporting must not prevent cleanup
            logger.warning("Anneal status callback failed: {!r}", error)

    # Establish shutter readiness before constructing or moving motion devices.
    # Keep this same connection for the scan; a separate preflight would race.
    status("Connecting to SC10")
    with SC10(
        port=config.sc10_port,
        baud_rate=config.sc10_baud_rate,
        timeout_s=config.sc10_timeout_s,
    ) as shutter:
        shutter.set_mode(SC10Mode.MANUAL)
        shutter.set_enabled(False)
        status("Connecting to rotation stage")
        with KinesisRotationStage(
            move_timeout_s=config.rotation_stage_timeout_s,
        ) as rotation_stage:
            status(
                "Moving rotation stage to anneal coordinate "
                f"{config.anneal_rotation_coordinate:g}"
            )
            rotation_stage.move_to(config.anneal_rotation_coordinate)
            def return_rotation_stage() -> None:
                status(
                    "Moving rotation stage to return coordinate "
                    f"{config.return_rotation_coordinate:g}"
                )
                rotation_stage.move_to(config.return_rotation_coordinate)

            cleanup = (
                (("return rotation stage", return_rotation_stage),)
                if config.return_rotation_stage
                else ()
            )
            with cleanup_actions(*cleanup):
                return _run_laser_anneal_without_rotation_stage(
                    config,
                    stop_event=stop_event,
                    progress_callback=progress_callback,
                    status_callback=status_callback,
                    _prepared_shutter=shutter,
                )
