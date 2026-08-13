from __future__ import annotations

import struct

from labtools.devices.labjack_u6 import LabJackU6


class _LJTickDAC:
    """Low-level I2C driver for the LJTick-DAC connected to a U6."""

    EEPROM_ADDRESS = 0x50
    DAC_ADDRESS = 0x12

    def __init__(self, device: LabJackU6, dio_pin: int):
        self.device = device
        self.scl_pin = dio_pin
        self.sda_pin = dio_pin + 1
        self._load_cal_constants()

    def _to_double(self, buff) -> float:
        right, left = struct.unpack("<Ii", struct.pack("B" * 8, *buff[0:8]))
        return float(left) + float(right) / (2 ** 32)

    def _load_cal_constants(self) -> None:
        data = self.device.i2c(
            self.EEPROM_ADDRESS, [64],
            NumI2CBytesToReceive=36,
            SDAPinNum=self.sda_pin,
            SCLPinNum=self.scl_pin,
        )
        response = data['I2CBytes']
        if 255 in response:
            raise RuntimeError(
                "LJTick-DAC calibration constants look invalid. "
                "Check the LJTick-DAC is connected properly."
            )
        self.slope_a = self._to_double(response[0:8])
        self.offset_a = self._to_double(response[8:16])
        self.slope_b = self._to_double(response[16:24])
        self.offset_b = self._to_double(response[24:32])

    def set_voltages(self, voltage_a: float, voltage_b: float) -> None:
        binary_a = int(voltage_a * self.slope_a + self.offset_a)
        self.device.i2c(
            self.DAC_ADDRESS,
            [48, binary_a // 256, binary_a % 256],
            SDAPinNum=self.sda_pin,
            SCLPinNum=self.scl_pin,
        )
        binary_b = int(voltage_b * self.slope_b + self.offset_b)
        self.device.i2c(
            self.DAC_ADDRESS,
            [49, binary_b // 256, binary_b % 256],
            SDAPinNum=self.sda_pin,
            SCLPinNum=self.scl_pin,
        )


class ScanningMirror:
    """Controls a scanning mirror via a LJTick-DAC on a LabJack U6.

    Parameters
    ----------
    device : LabJackU6
        Shared U6 connection (see :class:`~labtools.devices.labjack_u6.LabJackU6`).
    dio_pin : int
        The DIO pin that the LJTick-DAC DIOA is connected to (DIOB = dio_pin + 1).

    Usage::

        with LabJackU6() as lj:
            mirror = ScanningMirror(lj, dio_pin=2)
            mirror.move(1.5, -0.5)
    """

    def __init__(self, device: LabJackU6, dio_pin: int = 2):
        self._dac = _LJTickDAC(device, dio_pin)

    def move(self, x_voltage: float, y_voltage: float) -> None:
        """Set the mirror position by applying voltages to DAC A (x) and DAC B (y)."""
        self._dac.set_voltages(x_voltage, y_voltage)

    def home(self) -> None:
        """Return the mirror to the zero-voltage position."""
        self._dac.set_voltages(0.0, 0.0)
