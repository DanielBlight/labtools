"""Whole scanning-mirror tests with a fake borrowed LabJack; no u6 import."""

import importlib.util
import math
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest


def encoded(value):
    left = math.floor(value)
    right = round((value - left) * 2**32)
    return list(struct.pack("<Ii", right, left))


class FakeLabJack:
    def __init__(self, calibration=None):
        values = calibration or (1000.0, 100.0, 2000.0, 200.0)
        self.response = [byte for value in values for byte in encoded(value)] + [
            0,
            0,
            0,
            0,
        ]
        self.calls = []
        self.failure = None
        self.close_calls = 0

    def i2c(self, address, data, **kwargs):
        call = (address, list(data), kwargs)
        self.calls.append(call)
        if len(self.calls) > 1 and self.failure == len(self.calls) - 1:
            raise OSError(f"write {self.failure} failed")
        if address == 0x50:
            return {"I2CBytes": list(self.response)}
        return {}

    def close(self):
        self.close_calls += 1


@pytest.fixture
def module(monkeypatch):
    package = ModuleType("labtools.devices.labjack_u6")
    package.LabJackU6 = FakeLabJack
    monkeypatch.setitem(sys.modules, "labtools.devices.labjack_u6", package)
    source = Path(__file__).parents[1] / "src/labtools/devices/scanning_mirror.py"
    spec = importlib.util.spec_from_file_location("_fake_scanning_mirror", source)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def writes(device):
    return device.calls[1:]


def test_calibration_and_success_transcript_preserved(module):
    device = FakeLabJack()
    mirror = module.ScanningMirror(device, dio_pin=2)
    mirror.move(1.5, 2.25)
    assert device.calls[0] == (
        0x50,
        [64],
        {"NumI2CBytesToReceive": 36, "SDAPinNum": 3, "SCLPinNum": 2},
    )
    assert writes(device) == [
        (0x12, [48, 6, 64], {"SDAPinNum": 3, "SCLPinNum": 2}),
        (0x12, [49, 18, 92], {"SDAPinNum": 3, "SCLPinNum": 2}),
    ]
    assert device.close_calls == 0


@pytest.mark.parametrize("a,b", [(math.nan, 0), (0, math.inf), (0, -math.inf)])
def test_nonfinite_voltage_preflight_sends_no_dac_write(module, a, b):
    device = FakeLabJack()
    mirror = module.ScanningMirror(device)
    with pytest.raises(ValueError, match="finite"):
        mirror.move(a, b)
    assert writes(device) == []


@pytest.mark.parametrize("a,b", [(-1, 0), (0, 33)])
def test_out_of_range_calibrated_code_sends_no_dac_write(module, a, b):
    device = FakeLabJack(calibration=(1.0, 0.0, 2000.0, 0.0))
    mirror = module.ScanningMirror(device)
    with pytest.raises(ValueError, match="outside"):
        mirror.move(a, b)
    assert writes(device) == []


def test_nonfinite_calibrated_code_sends_no_dac_write(module):
    device = FakeLabJack(calibration=(1.0, 0.0, 1.0, 0.0))
    mirror = module.ScanningMirror(device)
    mirror._dac.slope_a = math.inf
    with pytest.raises(ValueError, match="calibrated"):
        mirror.move(1, 0)
    assert writes(device) == []


def test_boundary_codes_and_truncation(module):
    device = FakeLabJack(calibration=(1.0, 0.0, 1.0, 0.0))
    mirror = module.ScanningMirror(device)
    mirror.move(0.999, 65535.999)
    assert [call[1] for call in writes(device)] == [[48, 0, 0], [49, 255, 255]]


def test_a_write_failure_has_no_partial_movement_wrapper(module):
    device = FakeLabJack(calibration=(1, 0, 1, 0))
    mirror = module.ScanningMirror(device)
    device.failure = 1
    with pytest.raises(OSError, match="write 1"):
        mirror.move(1, 2)
    assert len(writes(device)) == 1


def test_b_write_failure_reports_partial_movement_without_extra_write(module):
    device = FakeLabJack(calibration=(1, 0, 1, 0))
    mirror = module.ScanningMirror(device)
    device.failure = 2
    with pytest.raises(module.MirrorPartialMovementError, match="uncertain") as caught:
        mirror.move(1, 2)
    assert isinstance(caught.value.__cause__, OSError)
    assert [call[1] for call in writes(device)] == [[48, 0, 1], [49, 0, 2]]
    assert device.close_calls == 0


def test_home_preserves_zero_zero_and_borrowed_ownership(module):
    device = FakeLabJack(calibration=(1, 0, 1, 0))
    mirror = module.ScanningMirror(device)
    mirror.home()
    assert [call[1] for call in writes(device)] == [[48, 0, 0], [49, 0, 0]]
    assert device.close_calls == 0
