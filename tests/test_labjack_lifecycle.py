"""Real wrapper loaded with a fake u6 module, never a connected device."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("failure", [None, "calibration", "both", "close"])
def test_labjack_startup_and_idempotent_close(monkeypatch, failure):
    calls = []

    class Fake:
        def getCalibrationData(self):
            calls.append("calibration")
            if failure in {"calibration", "both"}:
                raise ValueError("calibration failed")

        def close(self):
            calls.append("close")
            if failure in {"both", "close"}:
                raise OSError("close failed")

    monkeypatch.setitem(sys.modules, "u6", SimpleNamespace(U6=Fake))
    path = Path(__file__).resolve().parents[1] / "src/labtools/devices/labjack_u6.py"
    spec = importlib.util.spec_from_file_location("isolated_labjack", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    if failure in {"calibration", "both"}:
        with pytest.raises(ValueError, match="calibration") as caught:
            module.LabJackU6()
        assert calls == ["calibration", "close"]
        if failure == "both":
            assert "close failed" in caught.value.__notes__[0]
    else:
        device = module.LabJackU6()
        if failure == "close":
            with pytest.raises(OSError):
                device.close()
            assert not device._closed
        else:
            device.close()
            device.close()
            assert calls == ["calibration", "close"]
