"""Intensity-map configuration and checkpoint compatibility; no Qt or hardware imports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from labtools.simulation.map_devices import MODEL_VERSION

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
    backend: str = "real"
    simulation_seed: int = 0
    simulation_realtime: bool = True
    simulation_fail_after_points: int | None = None

    def validate(self) -> None:
        if self.backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        if type(self.simulation_seed) is not int or self.simulation_seed < 0:
            raise ValueError("simulation_seed must be a nonnegative integer")
        if type(self.simulation_realtime) is not bool:
            raise ValueError("simulation_realtime must be bool")
        if self.simulation_fail_after_points is not None and (
            type(self.simulation_fail_after_points) is not int
            or self.simulation_fail_after_points < 0
        ):
            raise ValueError("simulation_fail_after_points must be nonnegative or None")
        if not all(
            np.isfinite(v)
            for v in (
                self.integration_time_s,
                self.settle_time_s,
                self.safe_voltage_min_v,
                self.safe_voltage_max_v,
            )
        ):
            raise ValueError("Timing and voltage limits must be finite")
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
        signature = {
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
        if self.backend == "simulation":
            signature.update(
                backend="simulation",
                simulation_seed=self.simulation_seed,
                simulation_model=MODEL_VERSION,
            )
        return signature
