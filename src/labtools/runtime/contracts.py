"""Structural map-device contracts; real and synthetic implementations need no inheritance."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Mirror(Protocol):
    def move(self, x_voltage: float, y_voltage: float) -> None: ...
    def home(self) -> None: ...


class Gate(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...


class Counter(Protocol):
    def configure_channel(
        self,
        channel: int,
        *,
        threshold_v: float,
        edge: str,
        enabled: bool = True,
    ) -> None: ...

    def get_simultaneous_counts(
        self,
        channels: Sequence[int],
        integration_time_s: float,
    ) -> dict[int, int]: ...


MapDevices = tuple[Mirror, Gate, Counter]
