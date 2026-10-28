"""Application-owned synthetic LabJack state for shared manual/map composition."""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock

from labtools.simulation.map_devices import SimulatedMapState, SimulatedTimeController


@dataclass(frozen=True)
class SimulatedLabJackSnapshot:
    """Detached diagnostic state that cannot authorize or mutate device access."""

    x_v: float
    y_v: float
    gate_open: bool
    measurements: int
    closed: bool
    moves: int


class SharedSimulatedLabJackService:
    """Mirror/gate service backed by one application-owned synthetic state."""

    def __init__(
        self, state: SimulatedMapState, *, voltage_min_v=-10.0, voltage_max_v=10.0
    ):
        if not math.isfinite(voltage_min_v) or not math.isfinite(voltage_max_v):
            raise ValueError("Synthetic voltage limits must be finite")
        if voltage_min_v >= voltage_max_v:
            raise ValueError("Synthetic minimum voltage must be below maximum")
        self._state = state
        self._minimum = float(voltage_min_v)
        self._maximum = float(voltage_max_v)
        self._lock = RLock()

    def move(self, x_voltage, y_voltage):
        values = (float(x_voltage), float(y_voltage))
        with self._lock:
            if self._state.closed:
                raise RuntimeError("Simulated application state is closed")
            if not all(
                math.isfinite(v) and self._minimum <= v <= self._maximum for v in values
            ):
                raise ValueError("Simulated mirror voltage outside configured limits")
            self._state.x_v, self._state.y_v = values
            self._state.moves.append(values)

    def home(self):
        self.move(0.0, 0.0)

    def open_gate(self):
        with self._lock:
            if self._state.closed:
                raise RuntimeError("Simulated application state is closed")
            self._state.gate_open = True

    def close_gate(self):
        with self._lock:
            self._state.gate_open = False

    def snapshot(self):
        with self._lock:
            return SimulatedLabJackSnapshot(
                self._state.x_v,
                self._state.y_v,
                self._state.gate_open,
                self._state.measurements,
                self._state.closed,
                len(self._state.moves),
            )

    def close(self):
        with self._lock:
            if self._state.closed:
                return
            self._state.gate_open = False
            self._state.closed = True


def synthetic_counter_provider(state: SimulatedMapState):
    """Return a config-bound provider without creating a simulated IDQ session."""

    @contextmanager
    def provide(config):
        if state.closed:
            raise RuntimeError("Simulated application state is closed")
        yield SimulatedTimeController(state, config)

    return provide
