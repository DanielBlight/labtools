"""Per-acquisition device ownership and explicit backend selection, independent of Qt.

This is not a shared connection manager. Real imports remain inside the real branch.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from labtools.runtime.contracts import MapDevices

if TYPE_CHECKING:
    from labtools.config.intensity_map import IntensityMapConfig


@dataclass(frozen=True)
class MapTransportFactories:
    """Explicit trusted constructors; no device is opened during validation."""

    labjack: object
    counter: object
    mirror: object
    gate: object

    def validate(self):
        if not all(callable(factory) for factory in (self.labjack, self.counter, self.mirror, self.gate)):
            raise TypeError("All map transport factories must be callable")


@contextmanager
def open_map_devices(config: IntensityMapConfig, *, factories=None) -> Iterator[MapDevices]:
    """Yield mirror, gate, controller; never silently fall back to simulation."""
    if factories is not None:
        if not isinstance(factories, MapTransportFactories):
            raise TypeError("factories must be MapTransportFactories")
        factories.validate()
        if config.backend != "real":
            raise ValueError("Explicit transport factories require real-contract settings")
    if config.backend == "simulation":
        from labtools.simulation.map_devices import (
            SimulatedGate,
            SimulatedMapState,
            SimulatedMirror,
            SimulatedTimeController,
        )

        state = SimulatedMapState()
        mirror = SimulatedMirror(state, config)
        gate = SimulatedGate(state)
        controller = SimulatedTimeController(state, config)
        try:
            yield mirror, gate, controller
        finally:
            gate.close()
            state.closed = True
        return
    if config.backend != "real":
        raise ValueError("backend must be real or simulation")
    if factories is None:
        # Existing native imports remain lazy; explicit fake factories bypass them.
        from labtools.devices.idq_time_controller import IDQTimeController
        from labtools.devices.labjack_u6 import LabJackU6
        from labtools.devices.scanning_mirror import ScanningMirror
        from labtools.devices.spad_gate import SPADGate

        factories = MapTransportFactories(LabJackU6, IDQTimeController, ScanningMirror, SPADGate)
    with ExitStack() as stack:
        labjack = stack.enter_context(factories.labjack())
        controller = stack.enter_context(
            factories.counter(config.time_controller_address)
        )
        mirror = factories.mirror(labjack, dio_pin=config.mirror_dio_pin)
        gate = factories.gate(labjack, pin=config.spad_gate_pin)
        yield mirror, gate, controller
