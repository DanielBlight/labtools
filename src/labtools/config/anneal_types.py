"""Native-free anneal data contracts; acquisition module re-exports for compatibility."""

from dataclasses import dataclass
from pathlib import Path


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
    minimum_mirror_voltage_v: float = -10.0
    maximum_mirror_voltage_v: float = 10.0
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
    maximum_open_time_s: float = 43200.0
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
