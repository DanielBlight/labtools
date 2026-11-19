"""Synthetic laser state for operator rehearsal; never imports a device driver."""
import math
from dataclasses import dataclass


@dataclass
class LaserModel:
    simulated: bool
    connected: bool = False
    output: bool | None = None
    current_a: float = 0.080

    def execute(self, command, current=None):
        if not self.simulated:
            raise RuntimeError("Native laser execution is disabled in this workspace candidate")
        if command not in {"connect", "apply", "on", "off", "disconnect"}:
            raise ValueError("Unknown laser command")
        if command in {"apply", "on"}:
            if isinstance(current, bool):
                raise ValueError("Current must be finite and between 0 and 0.100 A")
            value = float(current)
            if not math.isfinite(value) or not 0 <= value <= 0.100:
                raise ValueError("Current must be finite and between 0 and 0.100 A")
        if command == "connect":
            if not self.connected:
                self.connected, self.output = True, False
        elif command == "disconnect":
            self.connected, self.output = False, None
        else:
            if not self.connected:
                raise RuntimeError("Connect the simulated laser first")
            if command in {"apply", "on"}:
                self.current_a = value
            if command == "on":
                self.output = True
            elif command == "off":
                self.output = False
        return self.status

    @property
    def status(self):
        if not self.simulated:
            return "Laser: unknown"
        if not self.connected:
            return "Laser: disconnected (simulated)"
        return "Laser: " + ("ON" if self.output else "OFF") + " (simulated)"
