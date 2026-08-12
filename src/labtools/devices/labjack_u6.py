import u6
import time


class LabJackU6:
    """Owns the connection to a single LabJack U6.

    Pass this object to any device that needs the U6 (e.g. ScanningMirror,
    SPADGate) so they share one connection without either owning it.

    Usage::

        with LabJackU6() as lj:
            mirror = ScanningMirror(lj, dio_pin=2)
            spad = SPADGate(lj, pin=0)
    """

    def __init__(self):
        self._dev = u6.U6()
        self._dev.getCalibrationData()
        time.sleep(0.5)

    # ------------------------------------------------------------------
    # Low-level pass-throughs used by device wrappers
    # ------------------------------------------------------------------

    def i2c(self, *args, **kwargs):
        return self._dev.i2c(*args, **kwargs)

    def set_digital_out(self, pin, state):
        """Set a digital output pin high (state=1) or low (state=0)."""
        self._dev.setDOState(pin, state)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        self._dev.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
