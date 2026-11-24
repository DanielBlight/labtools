"""Current range regression tests without hardware or Qt."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from labtools.runtime.hardware_laser import MAX_CURRENT_A, HardwareLaser


@pytest.mark.parametrize("command", ["apply", "on"])
@pytest.mark.parametrize("current", [0.0, 0.001, 0.02, 0.039, 0.04])
def test_current_range_reaches_device(command, current):
    device = Mock()
    device.get_current.return_value = current
    device.get_diode_output.return_value = False
    workspace = SimpleNamespace(_require_open=Mock(), hardware_ready=Mock(), _ownership=Mock())
    laser = HardwareLaser(workspace, factory=lambda: device)
    try:
        laser.submit("connect").result(3)
        laser.submit(command, current).result(3)
        device.set_current.assert_called_once_with(current)
        if command == "apply":
            device.enable_diode.assert_not_called()
        else:
            device.enable_diode.assert_called_once_with()
        assert MAX_CURRENT_A == 0.04
    finally:
        laser.submit("disconnect").result(3)
        laser.close()

@pytest.mark.parametrize("command", ["apply", "on"])
@pytest.mark.parametrize("current", [-0.001, 0.040001, float("nan"), float("inf"), -float("inf"), True, None])
def test_invalid_current_rejected_before_connection(command, current):
    factory = Mock()
    laser = HardwareLaser(SimpleNamespace(), factory=factory)
    try:
        with pytest.raises(ValueError):
            laser.submit(command, current)
        factory.assert_not_called()
        assert not laser.busy
    finally:
        laser.close()
