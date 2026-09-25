"""Direct serial wrapper for the Thorlabs SC10 shutter controller."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Self

import serial
from serial.tools import list_ports


class SC10Error(RuntimeError):
    """Raised when SC10 communication fails."""


class SC10Mode(IntEnum):
    MANUAL = 1
    AUTO = 2
    SINGLE = 3
    REPEAT = 4
    EXTERNAL_GATE = 5


class SC10TriggerMode(IntEnum):
    INTERNAL = 0
    EXTERNAL = 1


class SC10ExternalTriggerMode(IntEnum):
    FOLLOW_SHUTTER_OUTPUT = 0
    FOLLOW_CONTROLLER_OUTPUT = 1


@dataclass(frozen=True)
class SC10Device:
    port: str
    description: str
    hardware_id: str


@dataclass(frozen=True)
class SC10State:
    identifier: str
    enabled: bool
    closed: bool
    mode: SC10Mode
    trigger_mode: SC10TriggerMode
    external_trigger_mode: SC10ExternalTriggerMode
    open_time_ms: int
    close_time_ms: int
    repeat_count: int


class SC10:
    """Control an SC10 over RS-232, tolerating whitespace in command echoes."""

    def __init__(
        self,
        port: str = "COM4",
        *,
        baud_rate: int = 9600,
        timeout_s: float = 1.0,
        auto_connect: bool = False,
    ) -> None:
        self.port = port
        self.baud_rate = int(baud_rate)
        self.timeout_s = float(timeout_s)
        self._serial: serial.Serial | None = None
        if auto_connect:
            self.connect()

    @classmethod
    def list_devices(cls) -> list[SC10Device]:
        return [
            SC10Device(p.device, p.description or "", p.hwid or "")
            for p in list_ports.comports()
        ]

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> None:
        if self.is_connected:
            return
        try:
            self._serial = serial.Serial(
                self.port,
                self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout_s,
                write_timeout=self.timeout_s,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            identifier = self.identify()
        except Exception:
            self.close()
            raise
        if "SC10" not in identifier.upper():
            self.close()
            raise SC10Error(f"Device on {self.port} is not an SC10: {identifier!r}")

    def close(self) -> None:
        connection = self._serial
        self._serial = None
        if connection is not None and connection.is_open:
            connection.close()

    def _connection(self) -> serial.Serial:
        if self._serial is None or not self._serial.is_open:
            raise SC10Error("SC10 is not connected")
        return self._serial

    def _exchange(self, command: str) -> list[str]:
        connection = self._connection()
        command = command.strip()
        connection.reset_input_buffer()
        connection.write((command + "\r").encode("ascii"))
        connection.flush()
        raw = connection.read_until(b"> ")
        if not raw:
            raise TimeoutError(f"SC10 did not answer {command!r}")
        text = re.sub(r">\s*$", "", raw.decode("ascii", errors="replace"))
        lines = [
            " ".join(x.strip().split()) for x in re.split(r"[\r\n]+", text) if x.strip()
        ]
        if lines and lines[0].lower() == command.lower():
            lines.pop(0)
        return lines

    def _query(self, command: str) -> str:
        lines = self._exchange(command)
        if not lines:
            raise SC10Error(f"No value returned for {command!r}")
        return lines[-1]

    def _command(self, command: str) -> None:
        lines = self._exchange(command)
        if any("error" in x.lower() for x in lines):
            raise SC10Error(f"SC10 rejected {command!r}: {lines}")

    def identify(self) -> str:
        return self._query("id?")

    def is_enabled(self) -> bool:
        return bool(int(self._query("ens?")))

    def toggle_enable(self) -> None:
        self._command("ens")

    def set_enabled(self, enabled: bool) -> None:
        requested = bool(enabled)
        if self.is_enabled() != requested:
            self.toggle_enable()
        if self.is_enabled() != requested:
            raise SC10Error(f"Enable state did not change to {requested}")

    def is_closed(self) -> bool:
        return bool(int(self._query("closed?")))

    def set_mode(self, mode: SC10Mode | int) -> None:
        self._command(f"mode={int(SC10Mode(mode))}")

    def get_mode(self) -> SC10Mode:
        return SC10Mode(int(self._query("mode?")))

    def set_trigger_mode(self, mode: SC10TriggerMode | int) -> None:
        self._command(f"trig={int(SC10TriggerMode(mode))}")

    def get_trigger_mode(self) -> SC10TriggerMode:
        return SC10TriggerMode(int(self._query("trig?")))

    def set_external_trigger_mode(self, mode: SC10ExternalTriggerMode | int) -> None:
        self._command(f"xto={int(SC10ExternalTriggerMode(mode))}")

    def get_external_trigger_mode(self) -> SC10ExternalTriggerMode:
        return SC10ExternalTriggerMode(int(self._query("xto?")))

    def set_open_time_ms(self, value: int) -> None:
        if value < 0:
            raise ValueError("Open time cannot be negative")
        self._command(f"open={value}")

    def get_open_time_ms(self) -> int:
        return int(float(self._query("open?")))

    def set_close_time_ms(self, value: int) -> None:
        if value < 0:
            raise ValueError("Close time cannot be negative")
        self._command(f"shut={value}")

    def get_close_time_ms(self) -> int:
        return int(float(self._query("shut?")))

    def set_repeat_count(self, value: int) -> None:
        if not 1 <= value <= 99:
            raise ValueError("Repeat count must be from 1 to 99")
        self._command(f"rep={value}")

    def get_repeat_count(self) -> int:
        return int(self._query("rep?"))

    def get_state(self) -> SC10State:
        return SC10State(
            self.identify(),
            self.is_enabled(),
            self.is_closed(),
            self.get_mode(),
            self.get_trigger_mode(),
            self.get_external_trigger_mode(),
            self.get_open_time_ms(),
            self.get_close_time_ms(),
            self.get_repeat_count(),
        )

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
