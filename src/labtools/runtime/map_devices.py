"""Per-acquisition device ownership and explicit backend selection, independent of Qt.

This is not a shared connection manager. Real imports remain inside the real branch.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING

from labtools.runtime.contracts import MapDevices

if TYPE_CHECKING:
    from labtools.config.intensity_map import IntensityMapConfig


@contextmanager
def open_map_devices(config: IntensityMapConfig) -> Iterator[MapDevices]:
    """Yield mirror, gate, controller; never silently fall back to simulation."""
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
    # Import native libraries only after explicit real selection.
    from labtools.devices.idq_time_controller import IDQTimeController
    from labtools.devices.labjack_u6 import LabJackU6
    from labtools.devices.scanning_mirror import ScanningMirror
    from labtools.devices.spad_gate import SPADGate

    with ExitStack() as stack:
        labjack = stack.enter_context(LabJackU6())
        controller = stack.enter_context(
            IDQTimeController(config.time_controller_address)
        )
        mirror = ScanningMirror(labjack, dio_pin=config.mirror_dio_pin)
        gate = SPADGate(labjack, pin=config.spad_gate_pin)
        yield mirror, gate, controller
