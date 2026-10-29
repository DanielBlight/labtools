"""Whole UC480 wrapper tests with a fake lazy SDK; no camera or DLL."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from threading import get_ident
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


class FakeCamera:
    def __init__(self, owner):
        self.o = owner

    def _r(self, n, *a):
        self.o.events.append((n, *a))
        self.o.threads.append(get_ident())
        e = self.o.fail.get(n)
        e is not None and (_ for _ in ()).throw(e)

    def set_exposure(self, v):
        self._r("exposure", v)
        return v

    def get_exposure(self):
        return 0.02

    def setup_acquisition(self, **k):
        self._r("setup", k["nframes"])

    def start_acquisition(self):
        self._r("start")

    def stop_acquisition(self):
        self._r("stop")

    def close(self):
        self._r("close")

    def snap(self):
        return self.o.frame

    def wait_for_frame(self, **k):
        self._r("wait", k["timeout"])

    def read_newest_image(self):
        return self.o.frame

    def get_gains(self):
        return (1, 2, 3, 4)

    def get_max_gains(self):
        return (10, 10, 10, 10)

    def set_gains(self, **k):
        return (k["master"], 2, 3, 4)

    def get_device_info(self):
        return {"model": "fake"}


class SDK:
    def __init__(self):
        self.events = []
        self.threads = []
        self.fail = {}
        self.frame = np.arange(6).reshape(2, 3)
        self.camera = FakeCamera(self)

    def create(self, **k):
        self.events.append(("create", k))
        e = self.fail.get("create")
        e is not None and (_ for _ in ()).throw(e)
        return self.camera

    def list(self, **k):
        return [
            SimpleNamespace(
                cam_id=0,
                dev_id=1,
                model="fake",
                serial_number="S",
                in_use=False,
                status=0,
            )
        ]


@pytest.fixture
def env(monkeypatch):
    sdk = SDK()
    root = ModuleType("pylablib")
    devices = ModuleType("pylablib.devices")
    uc = ModuleType("pylablib.devices.uc480")
    uc.UC480Camera = sdk.create
    uc.list_cameras = sdk.list
    devices.uc480 = uc
    for n, m in [
        ("pylablib", root),
        ("pylablib.devices", devices),
        ("pylablib.devices.uc480", uc),
    ]:
        monkeypatch.setitem(sys.modules, n, m)
    src = Path(__file__).parents[1] / "src/labtools/devices/uc480_camera.py"
    spec = importlib.util.spec_from_file_location("_ucfake", src)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, mod)
    spec.loader.exec_module(mod)
    return mod, sdk


def test_lazy_import_and_selection(env):
    m, s = env
    assert m.ThorlabsUC480Camera.list_cameras()[0].camera_id == 0
    d = m.ThorlabsUC480Camera()
    d.connect()
    assert s.events[:2] == [
        ("create", {"cam_id": 0, "backend": "uc480"}),
        ("exposure", 0.02),
    ]
    d.close()


@pytest.mark.parametrize("stage", ["create", "exposure"])
def test_connect_failure_cleanup(env, stage):
    m, s = env
    s.fail[stage] = OSError(stage)
    d = m.ThorlabsUC480Camera()
    with pytest.raises(OSError):
        d.connect()
    if stage == "exposure":
        assert ("close",) in s.events


@pytest.mark.parametrize("kind", [OSError, KeyboardInterrupt, asyncio.CancelledError])
def test_start_failure_rolls_back_and_preserves_primary(env, kind):
    m, s = env
    d = m.ThorlabsUC480Camera()
    d.connect()
    e = kind("start")
    s.fail["start"] = e
    with pytest.raises(kind) as c:
        d.start_live()
    assert (
        c.value is e
        and s.events[-2:] == [("start",), ("stop",)]
        and d._acquisition_state == "idle"
    )


@pytest.mark.parametrize("kind", [OSError, KeyboardInterrupt, asyncio.CancelledError])
def test_start_and_rollback_failure_retained(env, kind):
    m, s = env
    d = m.ThorlabsUC480Camera()
    d.connect()
    e = kind("start")
    x = OSError("stop")
    s.fail.update(start=e, stop=x)
    with pytest.raises(kind) as c:
        d.start_live()
    assert c.value is e and e._uc480_cleanup_failures == (x,)


@pytest.mark.parametrize("stop,close", [(True, False), (False, True), (True, True)])
def test_close_attempts_both(env, stop, close):
    m, s = env
    d = m.ThorlabsUC480Camera()
    d.connect()
    d.start_live()
    if stop:
        s.fail["stop"] = OSError("stop")
    if close:
        s.fail["close"] = OSError("close")
    with pytest.raises(m.UC480CameraError) as c:
        d.close()
    assert len(c.value.__cause__.exceptions) == stop + close and s.events[-2:] == [
        ("stop",),
        ("close",),
    ]


@pytest.mark.parametrize("mirror", [False, True])
def test_owned_contiguous_frame(env, mirror):
    m, s = env
    d = m.ThorlabsUC480Camera(mirror_horizontal=mirror)
    d.connect()
    out = d.snap()
    expected = np.flip(s.frame, 1) if mirror else s.frame
    np.testing.assert_array_equal(out, expected)
    assert out.flags.c_contiguous and not np.shares_memory(out, s.frame)
    d.close()


def test_live_read_and_idempotent_close_thread(env):
    m, s = env
    d = m.ThorlabsUC480Camera()
    d.connect()
    d.start_live(buffer_frames=3)
    out = d.read_latest(timeout_s=0.5)
    assert out.flags.c_contiguous
    d.stop_live()
    d.close()
    before = list(s.events)
    d.close()
    assert s.events == before and set(s.threads) == {get_ident()}


def test_body_primary_survives_cleanup(env):
    m, s = env
    s.fail["close"] = OSError("close")
    primary = RuntimeError("body")
    with pytest.raises(RuntimeError) as c, m.ThorlabsUC480Camera():
        raise primary
    assert c.value is primary and primary._uc480_cleanup_failures
