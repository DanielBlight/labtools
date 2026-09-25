"""Wrapper for the sole connected Thorlabs Kinesis rotation stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self


class KinesisRotationStageError(RuntimeError):
    """Raised when Kinesis discovery or motion fails."""


@dataclass(frozen=True)
class KinesisDevice:
    serial_number: str
    description: str


class KinesisRotationStage:
    """Control the sole connected Kinesis stage in native controller units."""

    def __init__(self, *, move_timeout_s: float = 60.0) -> None:
        if move_timeout_s <= 0:
            raise ValueError("move_timeout_s must be greater than zero")
        self.move_timeout_s = float(move_timeout_s)
        self.serial_number: str | None = None
        self._stage = None

    @staticmethod
    def _module():
        try:
            from pylablib.devices import Thorlabs
        except ModuleNotFoundError as exc:
            missing = exc.name or "an optional dependency"
            raise KinesisRotationStageError(
                f"Kinesis support is missing {missing!r}. Run "
                "'uv add numba pyft232', then retry."
            ) from exc
        except ImportError as exc:
            raise KinesisRotationStageError(
                "Could not import pyLabLib Kinesis support. Install "
                "pylablib-lightweight, numba, and pyft232."
            ) from exc
        return Thorlabs

    @classmethod
    def list_devices(cls) -> list[KinesisDevice]:
        return [
            KinesisDevice(str(serial), str(description))
            for serial, description in cls._module().list_kinesis_devices()
        ]

    @property
    def is_connected(self) -> bool:
        return self._stage is not None

    def connect(self) -> None:
        if self.is_connected:
            return
        devices = self.list_devices()
        if len(devices) != 1:
            raise KinesisRotationStageError(
                f"Exactly one Kinesis device must be connected; found {len(devices)}."
            )
        self.serial_number = devices[0].serial_number
        try:
            self._stage = self._module().KinesisMotor(self.serial_number)
        except Exception as exc:
            self.close()
            raise KinesisRotationStageError(
                f"Could not connect to Kinesis device {self.serial_number!r}: {exc}"
            ) from exc

    def close(self) -> None:
        stage = self._stage
        self._stage = None
        if stage is not None:
            try:
                stage.close()
            except Exception as exc:
                raise KinesisRotationStageError(
                    f"Could not close Kinesis stage: {exc}"
                ) from exc

    def _connected_stage(self):
        if self._stage is None:
            raise KinesisRotationStageError("Kinesis stage is not connected")
        return self._stage

    def get_position(self) -> float:
        return float(self._connected_stage().get_position())

    def stop(self) -> None:
        self._connected_stage().stop()

    def move_to(self, position: float, *, wait: bool = True) -> float:
        stage = self._connected_stage()
        try:
            stage.move_to(float(position))
            if wait:
                stage.wait_move(timeout=self.move_timeout_s)
        except Exception as exc:
            raise KinesisRotationStageError(
                f"Could not move stage to {position:g}: {exc}"
            ) from exc
        return self.get_position()

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
