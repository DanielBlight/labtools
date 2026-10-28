from __future__ import annotations

import time
from typing import Self

import u6


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
        self._closed = False
        self._dev = u6.U6()
        try:
            self._dev.getCalibrationData()
            time.sleep(0.5)
        except BaseException as primary:
            try:
                self.close()
            except Exception as cleanup:  # noqa: BLE001 - preserve startup failure
                primary.add_note(f"Partial LabJack startup cleanup failed: {cleanup!r}")
            raise

    # ------------------------------------------------------------------
    # Low-level pass-throughs used by device wrappers
    # ------------------------------------------------------------------

    def i2c(self, *args, **kwargs):
        return self._dev.i2c(*args, **kwargs)

    def set_digital_out(self, pin: int, state: int) -> None:
        """Set a digital output pin high (state=1) or low (state=0)."""
        self._dev.setDOState(pin, state)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        if not self._closed:
            self._dev.close()
            self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_) -> None:
        self.close()
