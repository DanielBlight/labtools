"""Thorlabs ITC4000-series laser diode and TEC controller."""

from __future__ import annotations

import time

import pyvisa
from pyvisa.resources import MessageBasedResource


class ITC4000:
    """Control a Thorlabs ITC4000-series laser diode/TEC controller.

    The class owns one PyVISA resource session for its lifetime. All commands,
    identification queries, and state readbacks use that same session.

    Parameters
    ----------
    address:
        VISA resource address, for example
        ``USB0::0x1313::0x804A::M00739898::INSTR``.
    threshold_current:
        Current setpoint applied after the laser-diode output is disabled.
    max_current:
        Software safety ceiling in amperes. Current requests above this value
        are rejected before any SCPI command is sent. Set this to the approved
        limit for the connected laser diode and experimental configuration.
    timeout_ms:
        VISA I/O timeout in milliseconds.

    Notes
    -----
    This class does not create temporary VISA sessions for identification
    checks. The same instrument session is used for identification, readback,
    and control commands.
    """

    DEFAULT_ADDRESS = "USB0::0x1313::0x804A::M00739898::INSTR"

    def __init__(
        self,
        address: str | None = None,
        *,
        threshold_current: float = 0.049,
        max_current: float = 0.100,
        timeout_ms: int = 5000,
    ) -> None:
        """Open and configure the VISA connection."""
        self.address = address or self.DEFAULT_ADDRESS
        self.threshold_current = float(threshold_current)
        self.max_current = float(max_current)
        self._closed = False

        if self.threshold_current < 0:
            raise ValueError("threshold_current cannot be negative.")

        if self.max_current <= 0:
            raise ValueError("max_current must be greater than zero.")

        if self.threshold_current > self.max_current:
            raise ValueError(
                "threshold_current cannot exceed max_current."
            )

        self._rm = pyvisa.ResourceManager()

        self._itc: MessageBasedResource = self._rm.open_resource(
            self.address,
            timeout=timeout_ms,
        )

        self._itc.write_termination = "\n"
        self._itc.read_termination = "\n"

        # Clear stale status and error information from earlier sessions.
        self._itc.write("*CLS")

    # ------------------------------------------------------------------
    # Low-level checked communication
    # ------------------------------------------------------------------
    def _ensure_open(self) -> None:
        """Raise a clear error if code uses a closed VISA session."""
        if self._closed:
            raise RuntimeError(
                "The ITC4000 VISA session is closed."
            )

    def _query(self, command: str) -> str:
        """Send a SCPI query and return the stripped response."""
        self._ensure_open()
        return self._itc.query(command).strip()

    def _check_error(self, operation: str) -> None:
        """Raise an exception if the controller reports a SCPI error."""
        error = self._query("SYST:ERR?")

        if not error.startswith(("0", "+0")):
            raise RuntimeError(
                f"{operation} failed: {error}"
            )

    def _write_checked(
        self,
        command: str,
        operation: str,
    ) -> None:
        """Send a SCPI command, wait for completion, and check errors."""
        self._ensure_open()

        self._itc.write(command)

        # Wait for the previous command to complete.
        self._query("*OPC?")

        # Read the controller error queue immediately after the command.
        self._check_error(operation)

    # ------------------------------------------------------------------
    # Identification and state readback
    # ------------------------------------------------------------------
    def identify(self) -> str:
        """Return the instrument identification string from ``*IDN?``."""
        return self._query("*IDN?")

    def get_diode_output(self) -> bool:
        """Return ``True`` when the laser-diode output is enabled."""
        response = self._query("OUTP?")
        return bool(int(float(response)))

    def get_tec_output(self) -> bool:
        """Return ``True`` when the TEC output is enabled."""
        response = self._query("OUTP2?")
        return bool(int(float(response)))

    # ------------------------------------------------------------------
    # Laser-diode output
    # ------------------------------------------------------------------
    def enable_diode(self) -> None:
        """Enable the laser-diode output and verify its reported state."""
        self._write_checked(
            "OUTP ON",
            "Enable laser-diode output",
        )

        if not self.get_diode_output():
            raise RuntimeError(
                "The controller still reports the laser-diode output "
                "as OFF. Check the interlock, LD Enable input, and "
                "controller protection state."
            )

    def disable_diode(self) -> None:
        """Disable the laser-diode output and reset its current setpoint.

        The output is switched off before the current setpoint is changed.
        """
        self._write_checked(
            "OUTP OFF",
            "Disable laser-diode output",
        )

        if self.get_diode_output():
            raise RuntimeError(
                "The controller still reports the laser-diode output "
                "as ON."
            )

        self.set_current(self.threshold_current)

    # ------------------------------------------------------------------
    # TEC output
    # ------------------------------------------------------------------
    def enable_tec(self) -> None:
        """Enable the TEC output and verify its reported state."""
        self._write_checked(
            "OUTP2 ON",
            "Enable TEC output",
        )

        if not self.get_tec_output():
            raise RuntimeError(
                "The controller still reports the TEC output as OFF."
            )

    def disable_tec(self) -> None:
        """Disable the TEC output and verify its reported state."""
        self._write_checked(
            "OUTP2 OFF",
            "Disable TEC output",
        )

        if self.get_tec_output():
            raise RuntimeError(
                "The controller still reports the TEC output as ON."
            )

    # ------------------------------------------------------------------
    # Combined startup and shutdown sequencing
    # ------------------------------------------------------------------
    def enable(
        self,
        current: float,
        tec_stabilise_s: float = 5.0,
    ) -> None:
        """Enable the TEC, set current, then enable diode output.

        Parameters
        ----------
        current:
            Requested laser current in amperes.
        tec_stabilise_s:
            Delay after enabling a previously disabled TEC output. The delay
            is skipped if the controller already reports that the TEC is on.
        """
        if tec_stabilise_s < 0:
            raise ValueError(
                "tec_stabilise_s cannot be negative."
            )

        if not self.get_tec_output():
            self.enable_tec()
            time.sleep(tec_stabilise_s)

        self.set_current(current)
        self.enable_diode()

    def disable(
        self,
        *,
        disable_tec: bool = False,
    ) -> None:
        """Disable the laser-diode output.

        Parameters
        ----------
        disable_tec:
            Also disable the TEC when ``True``. The default leaves the TEC on
            to avoid unnecessary thermal cycling during a GUI session.
        """
        self.disable_diode()

        if disable_tec:
            self.disable_tec()

    # ------------------------------------------------------------------
    # Current and temperature
    # ------------------------------------------------------------------
    def set_current(self, current: float) -> None:
        """Set and verify the laser-current setpoint in amperes."""
        current = float(current)

        if not 0 <= current <= self.max_current:
            raise ValueError(
                f"Current must be between 0 and "
                f"{self.max_current:.6g} A; "
                f"received {current:.6g} A."
            )

        self._write_checked(
            f"SOUR:CURR {current:.9g}",
            f"Set laser current to {current:.9g} A",
        )

        readback = self.get_current()
        tolerance = max(
            1e-6,
            abs(current) * 1e-4,
        )

        if abs(readback - current) > tolerance:
            raise RuntimeError(
                f"Current readback mismatch: requested "
                f"{current:.9g} A, but the controller reports "
                f"{readback:.9g} A."
            )

    def get_current(self) -> float:
        """Return the laser-current setpoint in amperes."""
        return float(
            self._query("SOUR:CURR?")
        )

    def set_temperature(self, temperature: float) -> None:
        """Set the TEC temperature setpoint in degrees Celsius."""
        temperature = float(temperature)

        self._write_checked(
            f"SOUR2:TEMP {temperature:.9g}C",
            f"Set TEC temperature to "
            f"{temperature:.9g} degrees Celsius",
        )

    def get_temperature_setpoint(self) -> float:
        """Return the TEC temperature setpoint in degrees Celsius."""
        return float(
            self._query("SOUR2:TEMP?")
        )

    def get_temperature(self) -> float:
        """Return the measured temperature in degrees Celsius."""
        return float(
            self._query("MEAS:TEMP?")
        )

    # ------------------------------------------------------------------
    # Pulse settings
    # ------------------------------------------------------------------
    def set_pulse_frequency(self, frequency: float) -> None:
        """Set the pulse frequency in hertz."""
        frequency = float(frequency)

        if frequency <= 0:
            raise ValueError(
                "frequency must be greater than zero."
            )

        period = 1 / frequency

        self._write_checked(
            f"SOURce:PULSe:PERiod {period:.12g}",
            f"Set pulse frequency to {frequency:.9g} Hz",
        )

    def get_pulse_frequency(self) -> float:
        """Return the pulse frequency in hertz."""
        period = float(
            self._query("SOURce:PULSe:PERiod?")
        )

        return 1 / period

    def set_pulse_width(self, width: float) -> None:
        """Set the pulse width in seconds."""
        width = float(width)

        if width <= 0:
            raise ValueError(
                "width must be greater than zero."
            )

        self._write_checked(
            f"SOURce:PULSe:WIDTh {width:.12g}",
            f"Set pulse width to {width:.9g} s",
        )

    def get_pulse_width(self) -> float:
        """Return the pulse width in seconds."""
        return float(
            self._query("SOURce:PULSe:WIDTh?")
        )

    def set_pulse_duty_cycle(
        self,
        duty_cycle: float,
    ) -> None:
        """Set the pulse duty cycle in percent."""
        duty_cycle = float(duty_cycle)

        if not 0 < duty_cycle <= 100:
            raise ValueError(
                "duty_cycle must be greater than 0 and at most 100."
            )

        self._write_checked(
            f"SOURce:PULSe:DCYCle {duty_cycle:.9g}",
            f"Set pulse duty cycle to {duty_cycle:.9g}%",
        )

    def get_pulse_duty_cycle(self) -> float:
        """Return the pulse duty cycle in percent."""
        return float(
            self._query("SOURce:PULSe:DCYCle?")
        )

    def set_pulse_hold(self, parameter: str) -> None:
        """Choose whether pulse width or duty cycle remains constant.

        Parameters
        ----------
        parameter:
            Either ``"width"`` or ``"dcycle"``.
        """
        options = {
            "width": "WIDTh",
            "dcycle": "DCYCle",
        }

        key = parameter.lower()

        if key not in options:
            raise ValueError(
                "parameter must be 'width' or 'dcycle'; "
                f"received {parameter!r}."
            )

        self._write_checked(
            f"SOURce:PULSe:HOLD {options[key]}",
            f"Set pulse hold mode to {key}",
        )

    def get_pulse_hold(self) -> str:
        """Return the active pulse hold mode."""
        return self._query(
            "SOURce:PULSe:HOLD?"
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Close the instrument and resource-manager sessions."""
        if self._closed:
            return

        try:
            self._itc.close()
        finally:
            self._rm.close()
            self._closed = True

    def __enter__(self) -> "ITC4000":
        """Return the connected controller for a context manager."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close VISA sessions when leaving a context manager."""
        self.close()