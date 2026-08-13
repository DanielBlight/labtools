from __future__ import annotations

from labtools.devices.labjack_u6 import LabJackU6


class SPADGate:
    """Controls a SPAD gate connected to a digital output on a LabJack U6.

    Parameters
    ----------
    device : LabJackU6
        Shared U6 connection.
    pin : int
        Digital output pin the gate is wired to.

    Usage::

        with LabJackU6() as lj:
            gate = SPADGate(lj, pin=0)
            gate.open()
            # ... acquire ...
            gate.close()
    """

    def __init__(self, device: LabJackU6, pin: int = 0):
        self._device = device
        self._pin = pin

    def open(self) -> None:
        """Open the gate (enable SPAD counting)."""
        self._device.set_digital_out(self._pin, 1)

    def close(self) -> None:
        """Close the gate (disable SPAD counting)."""
        self._device.set_digital_out(self._pin, 0)
