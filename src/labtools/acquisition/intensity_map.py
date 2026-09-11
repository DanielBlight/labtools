"""Resumable scanning-mirror intensity-map acquisition.

Install as ``src/labtools/acquisition/intensity_map.py``.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from numpy.typing import NDArray

from labtools.devices.idq_time_controller import IDQTimeController
from labtools.devices.labjack_u6 import LabJackU6
from labtools.devices.scanning_mirror import ScanningMirror
from labtools.devices.spad_gate import SPADGate

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
ProgressCallback = Callable[["IntensityMapSnapshot"], None]
CancelCallback = Callable[[], bool]

CHECKPOINT_FILENAME = "intensity_map_checkpoint.npz"
METADATA_FILENAME = "intensity_map_metadata.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class IntensityMapConfig:
    """Configuration for a one- or two-channel intensity map."""

    x_start_v: float
    x_stop_v: float
    x_points: int
    y_start_v: float
    y_stop_v: float
    y_points: int
    integration_time_s: float = 0.100
    channels: tuple[int, ...] = (1,)
    settle_time_s: float = 0.010
    time_controller_address: str = "169.254.99.159"
    channel_thresholds_v: tuple[float, ...] = (0.1,)
    channel_edges: tuple[str, ...] = ("rising",)
    mirror_dio_pin: int = 2
    spad_gate_pin: int = 0
    serpentine: bool = True
    output_root: Path = Path("C:/LabData/IntensityMaps")
    save_results: bool = True
    safe_voltage_min_v: float = -10.0
    safe_voltage_max_v: float = 10.0
    checkpoint_every_points: int = 10

    def validate(self) -> None:
        if self.x_points < 2 or self.y_points < 2:
            raise ValueError("x_points and y_points must each be at least 2.")
        if self.integration_time_s <= 0:
            raise ValueError("integration_time_s must be greater than zero.")
        if self.settle_time_s < 0:
            raise ValueError("settle_time_s cannot be negative.")
        if not 1 <= len(self.channels) <= 2:
            raise ValueError("Select one or two Time Controller channels.")
        if len(set(self.channels)) != len(self.channels):
            raise ValueError("Time Controller channels must be unique.")
        if any(channel not in {1, 2, 3, 4} for channel in self.channels):
            raise ValueError("Time Controller channels must be in the range 1 to 4.")
        if len(self.channel_thresholds_v) != len(self.channels):
            raise ValueError("Provide one threshold for each selected channel.")
        if len(self.channel_edges) != len(self.channels):
            raise ValueError("Provide one slope orientation for each selected channel.")
        if any(not np.isfinite(value) for value in self.channel_thresholds_v):
            raise ValueError("All channel thresholds must be finite.")
        if any(edge not in {"rising", "falling"} for edge in self.channel_edges):
            raise ValueError("Channel slopes must be 'rising' or 'falling'.")
        if self.safe_voltage_min_v >= self.safe_voltage_max_v:
            raise ValueError("safe_voltage_min_v must be below safe_voltage_max_v.")
        for name, value in {
            "x_start_v": self.x_start_v,
            "x_stop_v": self.x_stop_v,
            "y_start_v": self.y_start_v,
            "y_stop_v": self.y_stop_v,
        }.items():
            if not self.safe_voltage_min_v <= value <= self.safe_voltage_max_v:
                raise ValueError(
                    f"{name}={value} V is outside the configured safe range "
                    f"[{self.safe_voltage_min_v}, {self.safe_voltage_max_v}] V."
                )
        if self.checkpoint_every_points < 1:
            raise ValueError("checkpoint_every_points must be at least 1.")

    def checkpoint_signature(self) -> dict[str, Any]:
        """Return settings that must match exactly when a map is resumed."""
        return {
            "schema_version": SCHEMA_VERSION,
            "x_start_v": self.x_start_v,
            "x_stop_v": self.x_stop_v,
            "x_points": self.x_points,
            "y_start_v": self.y_start_v,
            "y_stop_v": self.y_stop_v,
            "y_points": self.y_points,
            "integration_time_s": self.integration_time_s,
            "channels": list(self.channels),
            "settle_time_s": self.settle_time_s,
            "time_controller_address": self.time_controller_address,
            "channel_thresholds_v": list(self.channel_thresholds_v),
            "channel_edges": list(self.channel_edges),
            "mirror_dio_pin": self.mirror_dio_pin,
            "spad_gate_pin": self.spad_gate_pin,
            "serpentine": self.serpentine,
        }


@dataclass(frozen=True)
class IntensityMapSnapshot:
    """Immutable progress state supplied to plotting and GUI callbacks."""

    x_values_v: FloatArray
    y_values_v: FloatArray
    channels: tuple[int, ...]
    count_rates_cps: FloatArray
    summed_count_rate_cps: FloatArray
    completed_mask: BoolArray
    points_complete: int
    total_points: int
    elapsed_s: float
    output_directory: Path
    resumed: bool


@dataclass(frozen=True)
class IntensityMapResult:
    """Completed or deliberately stopped intensity-map acquisition."""

    x_values_v: FloatArray
    y_values_v: FloatArray
    channels: tuple[int, ...]
    counts: NDArray[np.int64]
    count_rates_cps: FloatArray
    summed_count_rate_cps: FloatArray
    completed_mask: BoolArray
    timestamps_unix_s: FloatArray
    elapsed_s: float
    output_directory: Path
    complete: bool
    resumed: bool


def _scan_indices(config: IntensityMapConfig):
    for y_index in range(config.y_points):
        indices = range(config.x_points)
        if config.serpentine and y_index % 2:
            indices = range(config.x_points - 1, -1, -1)
        for x_index in indices:
            yield y_index, x_index


def _new_output_directory(root: Path) -> Path:
    path = Path(root) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path.mkdir(parents=True, exist_ok=False)
    return path


def _atomic_savez(path: Path, **arrays: Any) -> None:
    """Write a checkpoint robustly on Windows.

    A temporary file is written in the destination directory. Replacement is
    retried because antivirus and indexing services can briefly lock an existing
    checkpoint on Windows. If the lock persists, the newest state is retained
    under a recovery filename and can be selected automatically when resuming.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.{os.getpid()}.tmp.npz")

    try:
        np.savez_compressed(temporary, **arrays)
        last_error: PermissionError | None = None

        for attempt in range(10):
            try:
                os.replace(temporary, path)
                return
            except PermissionError as exc:
                last_error = exc
                logger.warning(
                    "Checkpoint is temporarily locked; retrying ({}/10).",
                    attempt + 1,
                )
                time.sleep(0.05 * (attempt + 1))

        recovery = path.with_name(
            f"{path.stem}.recovery-{datetime.now():%Y%m%d-%H%M%S-%f}{path.suffix}"
        )
        shutil.move(str(temporary), str(recovery))
        logger.error(
            "Windows kept {} locked. The newest checkpoint was preserved as {}. "
            "Resume will use the newest valid checkpoint.",
            path,
            recovery,
        )
        if last_error is not None:
            logger.debug("Final checkpoint replacement error: {!r}", last_error)
    finally:
        temporary.unlink(missing_ok=True)


def _write_metadata(
    output_directory: Path,
    config: IntensityMapConfig,
    *,
    initial_started_at: str,
    session_started_at: str,
    resume_sessions: int,
    complete: bool,
) -> None:
    payload = asdict(config)
    payload["channels"] = list(config.channels)
    payload["output_root"] = str(config.output_root)
    payload.update(
        {
            "schema_version": SCHEMA_VERSION,
            "checkpoint_signature": config.checkpoint_signature(),
            "initial_started_at": initial_started_at,
            "last_session_started_at": session_started_at,
            "resume_sessions": resume_sessions,
            "complete": complete,
        }
    )
    target = output_directory / METADATA_FILENAME
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def _load_metadata(output_directory: Path) -> dict[str, Any]:
    path = output_directory / METADATA_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"Resume metadata was not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_resume_config(
    config: IntensityMapConfig,
    metadata: dict[str, Any],
) -> None:
    saved = metadata.get("checkpoint_signature")
    current = config.checkpoint_signature()
    if saved != current:
        differing = sorted(
            key
            for key in set(saved or {}) | set(current)
            if (saved or {}).get(key) != current.get(key)
        )
        raise ValueError(
            "The selected checkpoint does not match the requested map "
            f"configuration. Differing fields: {', '.join(differing)}."
        )


def _save_checkpoint(
    output_directory: Path,
    *,
    x_values_v: FloatArray,
    y_values_v: FloatArray,
    channels: Sequence[int],
    counts: NDArray[np.int64],
    count_rates_cps: FloatArray,
    completed_mask: BoolArray,
    timestamps_unix_s: FloatArray,
) -> None:
    _atomic_savez(
        output_directory / CHECKPOINT_FILENAME,
        x_values_v=x_values_v,
        y_values_v=y_values_v,
        channels=np.asarray(channels, dtype=np.int64),
        counts=counts,
        count_rates_cps=count_rates_cps,
        completed_mask=completed_mask,
        timestamps_unix_s=timestamps_unix_s,
    )


def _load_checkpoint(output_directory: Path, config: IntensityMapConfig):
    main_path = output_directory / CHECKPOINT_FILENAME
    candidates = [
        path
        for path in (
            main_path,
            *output_directory.glob("intensity_map_checkpoint.recovery-*.npz"),
        )
        if path.exists()
    ]
    if not candidates:
        raise FileNotFoundError(f"Resume checkpoint was not found: {main_path}")
    path = max(candidates, key=lambda candidate: candidate.stat().st_mtime_ns)
    logger.info("Loading resume checkpoint {}", path)
    with np.load(path, allow_pickle=False) as data:
        x_values = np.asarray(data["x_values_v"], dtype=float)
        y_values = np.asarray(data["y_values_v"], dtype=float)
        channels = tuple(int(x) for x in data["channels"])
        counts = np.asarray(data["counts"], dtype=np.int64)
        rates = np.asarray(data["count_rates_cps"], dtype=float)
        completed = np.asarray(data["completed_mask"], dtype=bool)
        timestamps = np.asarray(data["timestamps_unix_s"], dtype=float)

    expected_map_shape = (config.y_points, config.x_points)
    expected_channel_shape = (len(config.channels), *expected_map_shape)
    if x_values.shape != (config.x_points,) or y_values.shape != (config.y_points,):
        raise ValueError("Checkpoint coordinate dimensions do not match the map.")
    if channels != config.channels:
        raise ValueError("Checkpoint channels do not match the requested channels.")
    if counts.shape != expected_channel_shape or rates.shape != expected_channel_shape:
        raise ValueError("Checkpoint channel arrays have unexpected dimensions.")
    if completed.shape != expected_map_shape or timestamps.shape != expected_map_shape:
        raise ValueError("Checkpoint completion arrays have unexpected dimensions.")
    return x_values, y_values, counts, rates, completed, timestamps


def _get_simultaneous_counts(
    controller: IDQTimeController,
    channels: Sequence[int],
    duration_s: float,
) -> dict[int, int]:
    """Acquire all selected channel counters during one shared record window.

    This uses the controller wrapper's SCPI helpers so two channels are sampled
    over the same acquisition interval instead of in consecutive intervals.
    """
    for channel in channels:
        controller._cmd(f"INPU{channel}:COUN:MODE ACCU;RESEt")  # noqa: SLF001
    controller._run_record(int(duration_s * 1e12))  # noqa: SLF001
    values: dict[int, int] = {}
    for channel in channels:
        response = controller._query(f"INPU{channel}:COUNter?")  # noqa: SLF001
        match = re.match(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", response.strip())
        if match is None:
            raise ValueError(
                f"Could not parse channel {channel} count response {response!r}."
            )
        values[channel] = int(float(match.group(0)))
    return values


def _snapshot(
    *,
    x_values: FloatArray,
    y_values: FloatArray,
    config: IntensityMapConfig,
    rates: FloatArray,
    completed: BoolArray,
    start_monotonic: float,
    output_directory: Path,
    resumed: bool,
) -> IntensityMapSnapshot:
    summed = np.nansum(rates, axis=0)
    summed[~completed] = np.nan
    return IntensityMapSnapshot(
        x_values_v=x_values.copy(),
        y_values_v=y_values.copy(),
        channels=config.channels,
        count_rates_cps=rates.copy(),
        summed_count_rate_cps=summed,
        completed_mask=completed.copy(),
        points_complete=int(np.count_nonzero(completed)),
        total_points=int(completed.size),
        elapsed_s=time.monotonic() - start_monotonic,
        output_directory=output_directory,
        resumed=resumed,
    )


def _save_final_outputs(result: IntensityMapResult, config: IntensityMapConfig) -> None:
    output = result.output_directory
    for channel_index, channel in enumerate(result.channels):
        matrix_path = output / f"channel_{channel}_count_rate_matrix.csv"
        with matrix_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["y_v / x_v", *result.x_values_v.tolist()])
            for y_value, row in zip(
                result.y_values_v,
                result.count_rates_cps[channel_index],
                strict=True,
            ):
                writer.writerow([float(y_value), *row.tolist()])

    with (output / "intensity_map_points.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        header = ["x_index", "y_index", "x_voltage_v", "y_voltage_v"]
        for channel in result.channels:
            header.extend([f"channel_{channel}_counts", f"channel_{channel}_cps"])
        header.extend(["summed_cps", "timestamp_unix_s", "complete"])
        writer.writerow(header)
        for y_index, y_value in enumerate(result.y_values_v):
            for x_index, x_value in enumerate(result.x_values_v):
                row: list[Any] = [x_index, y_index, float(x_value), float(y_value)]
                for channel_index in range(len(result.channels)):
                    row.extend(
                        [
                            int(result.counts[channel_index, y_index, x_index]),
                            float(
                                result.count_rates_cps[
                                    channel_index, y_index, x_index
                                ]
                            ),
                        ]
                    )
                row.extend(
                    [
                        float(result.summed_count_rate_cps[y_index, x_index]),
                        float(result.timestamps_unix_s[y_index, x_index]),
                        bool(result.completed_mask[y_index, x_index]),
                    ]
                )
                writer.writerow(row)

    np.savez_compressed(
        output / "intensity_map_complete.npz",
        x_values_v=result.x_values_v,
        y_values_v=result.y_values_v,
        channels=np.asarray(result.channels, dtype=np.int64),
        counts=result.counts,
        count_rates_cps=result.count_rates_cps,
        summed_count_rate_cps=result.summed_count_rate_cps,
        completed_mask=result.completed_mask,
        timestamps_unix_s=result.timestamps_unix_s,
    )

    from labtools.visualisation.intensity_map import plot_intensity_map

    figure, _ = plot_intensity_map(
        result.x_values_v,
        result.y_values_v,
        result.summed_count_rate_cps,
        title=_plot_title(result.channels),
        output_path=output / "summed_intensity_map.png",
        show=False,
    )
    import matplotlib.pyplot as plt

    plt.close(figure)


def _plot_title(channels: Sequence[int]) -> str:
    if len(channels) == 1:
        return f"Channel {channels[0]} intensity map"
    return f"Channels {channels[0]} + {channels[1]} intensity map"


def acquire_intensity_map(
    config: IntensityMapConfig,
    *,
    resume_directory: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_requested: CancelCallback | None = None,
) -> IntensityMapResult:
    """Acquire a new map or resume unfinished positions from a checkpoint."""
    config.validate()
    resumed = resume_directory is not None
    session_started_at = datetime.now().isoformat(timespec="seconds")

    if resumed:
        output_directory = Path(resume_directory).expanduser().resolve()
        metadata = _load_metadata(output_directory)
        _validate_resume_config(config, metadata)
        (
            x_values,
            y_values,
            counts,
            rates,
            completed,
            timestamps,
        ) = _load_checkpoint(output_directory, config)
        initial_started_at = str(metadata["initial_started_at"])
        resume_sessions = int(metadata.get("resume_sessions", 0)) + 1
    else:
        output_directory = _new_output_directory(config.output_root)
        x_values = np.linspace(config.x_start_v, config.x_stop_v, config.x_points)
        y_values = np.linspace(config.y_start_v, config.y_stop_v, config.y_points)
        shape = (len(config.channels), config.y_points, config.x_points)
        counts = np.full(shape, -1, dtype=np.int64)
        rates = np.full(shape, np.nan, dtype=float)
        completed = np.zeros((config.y_points, config.x_points), dtype=bool)
        timestamps = np.full((config.y_points, config.x_points), np.nan, dtype=float)
        initial_started_at = session_started_at
        resume_sessions = 0
        _save_checkpoint(
            output_directory,
            x_values_v=x_values,
            y_values_v=y_values,
            channels=config.channels,
            counts=counts,
            count_rates_cps=rates,
            completed_mask=completed,
            timestamps_unix_s=timestamps,
        )

    _write_metadata(
        output_directory,
        config,
        initial_started_at=initial_started_at,
        session_started_at=session_started_at,
        resume_sessions=resume_sessions,
        complete=False,
    )

    start_monotonic = time.monotonic()
    acquired_this_session = 0
    interrupted = False

    try:
        with LabJackU6() as labjack, IDQTimeController(
            config.time_controller_address
        ) as controller:
            mirror = ScanningMirror(labjack, dio_pin=config.mirror_dio_pin)
            gate = SPADGate(labjack, pin=config.spad_gate_pin)

            for channel, threshold_v, edge in zip(
                config.channels,
                config.channel_thresholds_v,
                config.channel_edges,
                strict=True,
            ):
                controller.configure_channel(
                    channel,
                    threshold_v=threshold_v,
                    edge=edge,
                    enabled=True,
                )

            gate.open()
            try:
                for y_index, x_index in _scan_indices(config):
                    if completed[y_index, x_index]:
                        continue
                    if cancel_requested is not None and cancel_requested():
                        interrupted = True
                        logger.warning("Map stopped at the user's request.")
                        break

                    x_voltage = float(x_values[x_index])
                    y_voltage = float(y_values[y_index])
                    mirror.move(x_voltage, y_voltage)
                    if config.settle_time_s:
                        time.sleep(config.settle_time_s)

                    measured = _get_simultaneous_counts(
                        controller,
                        config.channels,
                        config.integration_time_s,
                    )
                    for channel_index, channel in enumerate(config.channels):
                        value = measured[channel]
                        counts[channel_index, y_index, x_index] = value
                        rates[channel_index, y_index, x_index] = (
                            value / config.integration_time_s
                        )
                    completed[y_index, x_index] = True
                    timestamps[y_index, x_index] = time.time()
                    acquired_this_session += 1

                    if (
                        acquired_this_session % config.checkpoint_every_points == 0
                    ):
                        _save_checkpoint(
                            output_directory,
                            x_values_v=x_values,
                            y_values_v=y_values,
                            channels=config.channels,
                            counts=counts,
                            count_rates_cps=rates,
                            completed_mask=completed,
                            timestamps_unix_s=timestamps,
                        )

                    snap = _snapshot(
                        x_values=x_values,
                        y_values=y_values,
                        config=config,
                        rates=rates,
                        completed=completed,
                        start_monotonic=start_monotonic,
                        output_directory=output_directory,
                        resumed=resumed,
                    )
                    logger.info(
                        "Point {}/{}: x={:.4f} V, y={:.4f} V, rates={} cps",
                        snap.points_complete,
                        snap.total_points,
                        x_voltage,
                        y_voltage,
                        [
                            round(rates[i, y_index, x_index], 3)
                            for i in range(len(config.channels))
                        ],
                    )
                    if progress_callback is not None:
                        progress_callback(snap)
            finally:
                _save_checkpoint(
                    output_directory,
                    x_values_v=x_values,
                    y_values_v=y_values,
                    channels=config.channels,
                    counts=counts,
                    count_rates_cps=rates,
                    completed_mask=completed,
                    timestamps_unix_s=timestamps,
                )
                mirror.home()
                gate.close()
    except Exception:
        _save_checkpoint(
            output_directory,
            x_values_v=x_values,
            y_values_v=y_values,
            channels=config.channels,
            counts=counts,
            count_rates_cps=rates,
            completed_mask=completed,
            timestamps_unix_s=timestamps,
        )
        logger.exception(
            "Intensity-map acquisition failed; partial data are saved in {}",
            output_directory,
        )
        raise

    elapsed_s = time.monotonic() - start_monotonic
    complete = bool(np.all(completed)) and not interrupted
    summed = np.nansum(rates, axis=0)
    summed[~completed] = np.nan
    result = IntensityMapResult(
        x_values_v=x_values,
        y_values_v=y_values,
        channels=config.channels,
        counts=counts,
        count_rates_cps=rates,
        summed_count_rate_cps=summed,
        completed_mask=completed,
        timestamps_unix_s=timestamps,
        elapsed_s=elapsed_s,
        output_directory=output_directory,
        complete=complete,
        resumed=resumed,
    )
    if config.save_results:
        _save_final_outputs(result, config)
    _write_metadata(
        output_directory,
        config,
        initial_started_at=initial_started_at,
        session_started_at=session_started_at,
        resume_sessions=resume_sessions,
        complete=complete,
    )
    if complete:
        (output_directory / CHECKPOINT_FILENAME).unlink(missing_ok=True)

    return result


def config_from_resume_directory(path: str | Path) -> IntensityMapConfig:
    """Reconstruct a configuration from saved map metadata."""
    directory = Path(path).expanduser().resolve()
    metadata = _load_metadata(directory)
    known = {
        field
        for field in IntensityMapConfig.__dataclass_fields__
        if field in metadata
    }
    values = {field: metadata[field] for field in known}
    values["channels"] = tuple(int(channel) for channel in metadata["channels"])
    values["channel_thresholds_v"] = tuple(
        float(value) for value in metadata["channel_thresholds_v"]
    )
    values["channel_edges"] = tuple(str(value) for value in metadata["channel_edges"])
    values["output_root"] = Path(metadata["output_root"])
    return IntensityMapConfig(**values)


def estimated_minimum_duration_s(config: IntensityMapConfig) -> float:
    """Return integration-plus-settling time, excluding communication overhead."""
    return config.x_points * config.y_points * (
        config.integration_time_s + config.settle_time_s
    )


def main() -> None:
    config = IntensityMapConfig(
        x_start_v=-2.2,
        x_stop_v=-1.8,
        x_points=3,
        y_start_v=-0.7,
        y_stop_v=-0.3,
        y_points=3,
        integration_time_s=0.100,
        channels=(1,),
        channel_thresholds_v=(0.1,),
        channel_edges=("rising",),
        time_controller_address="169.254.99.159",
    )
    result = acquire_intensity_map(config)
    print(f"Map saved to {result.output_directory}")


if __name__ == "__main__":
    main()
