import pyvisa
import time


class ITC4000:
    """Wrapper for the Thorlabs ITC4000 laser diode / TEC controller.

    Manages the VISA connection and provides safe startup/shutdown sequencing
    (TEC on before diode, current ramped to threshold before diode off).

    Parameters
    ----------
    address : str
        VISA resource address, e.g. ``'USB0::0x1313::0x804A::M00739898::INSTR'``.
    threshold_current : float
        Current (A) to ramp down to before turning the diode off.
        Defaults to 0.049 A.

    Usage::

        with ITC4000('USB0::0x1313::0x804A::M00739898::INSTR') as laser:
            laser.enable(current=0.08)
            # ... experiment ...
        # on exit: current ramped to threshold, diode off, TEC off
    """

    def __init__(self, address, threshold_current=0.049):
        self._rm = pyvisa.ResourceManager()
        self._itc = self._rm.open_resource(address)
        self.threshold_current = threshold_current

    # ------------------------------------------------------------------
    # Laser diode
    # ------------------------------------------------------------------

    def enable_diode(self):
        """Turn on the laser diode output."""
        self._itc.write("OUTP ON")

    def disable_diode(self):
        """Ramp current to threshold then turn off the laser diode output."""
        self.set_current(self.threshold_current)
        self._itc.write("OUTP OFF")

    # ------------------------------------------------------------------
    # TEC
    # ------------------------------------------------------------------

    def enable_tec(self):
        """Turn on the TEC."""
        self._itc.write("OUTP2 ON")

    def disable_tec(self):
        """Turn off the TEC."""
        self._itc.write("OUTP2 OFF")

    # ------------------------------------------------------------------
    # Combined enable / disable (safe sequencing)
    # ------------------------------------------------------------------

    def enable(self, current, tec_stabilise_s=5):
        """Enable the TEC then the diode at the requested current.

        Parameters
        ----------
        current : float
            Drive current in amps.
        tec_stabilise_s : float
            Seconds to wait after enabling TEC before turning on the diode.
        """
        self.enable_tec()
        time.sleep(tec_stabilise_s)
        self.set_current(current)
        self.enable_diode()

    def disable(self):
        """Safely shut down: ramp diode current to threshold, diode off, TEC off."""
        self.disable_diode()
        self.disable_tec()

    # ------------------------------------------------------------------
    # Current and temperature
    # ------------------------------------------------------------------

    def set_current(self, current):
        """Set the diode drive current in amps."""
        self._itc.write(f"SOUR:CURR {current}")

    def get_current(self):
        """Return the set drive current in amps."""
        return float(self._itc.query("SOUR:CURR?"))

    def set_temperature(self, temperature):
        """Set the TEC target temperature in degrees Celsius."""
        self._itc.write(f"SOUR:TEMP {temperature}C")

    def get_temperature(self):
        """Return the TEC set temperature in degrees Celsius."""
        return float(self._itc.query("SOUR:TEMP?"))

    # ------------------------------------------------------------------
    # Pulse settings
    # ------------------------------------------------------------------

    def set_pulse_frequency(self, frequency):
        """Set the pulse frequency in Hz."""
        self._itc.write(f"SOURce:PULSe:PERiod {1 / frequency}")

    def get_pulse_frequency(self):
        """Return the pulse frequency in Hz."""
        return 1 / float(self._itc.query("SOURce:PULSe:PERiod?"))

    def set_pulse_width(self, width):
        self._itc.write(f"SOURce:PULSe:WIDTh {width}")

    def get_pulse_width(self):
        return float(self._itc.query("SOURce:PULSe:WIDTh?"))

    def set_pulse_duty_cycle(self, duty_cycle):
        self._itc.write(f"SOURce:PULSe:DCYCle {duty_cycle}")

    def get_pulse_duty_cycle(self):
        return float(self._itc.query("SOURce:PULSe:DCYCle?"))

    def set_pulse_hold(self, parameter):
        """Set whether pulse timing holds 'width' or 'dcycle' constant."""
        options = {"width": "WIDTh", "dcycle": "DCYCle"}
        key = parameter.lower()
        if key not in options:
            raise ValueError(f"parameter must be 'width' or 'dcycle', got {parameter!r}")
        self._itc.write(f"SOURce:PULSe:HOLD {options[key]}")

    def get_pulse_hold(self):
        return self._itc.query("SOURce:PULSe:HOLD?").strip()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Release the VISA resource."""
        self._itc.close()
        self._rm.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
