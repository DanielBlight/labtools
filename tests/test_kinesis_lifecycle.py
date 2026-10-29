import asyncio
import importlib.util
import sys
from pathlib import Path
from threading import get_ident
from types import ModuleType

import pytest


class SDK:
    def __init__(self):
        self.devices = [("123", "stage")]
        self.events = []
        self.fail = {}
        self.pos = 0

    def r(self, n, *a):
        self.events.append((n, *a, get_ident()))
        e = self.fail.get(n)
        e is not None and (_ for _ in ()).throw(e)

    def list(self):
        self.r("list")
        return self.devices

    def motor(self, s):
        self.r("open", s)
        return self

    def move_to(self, p):
        self.r("move", p)
        self.pos = p

    def wait_move(self, timeout):
        self.r("wait", timeout)

    def get_position(self):
        self.r("position")
        return self.pos

    def stop(self):
        self.r("stop")

    def close(self):
        self.r("close")


@pytest.fixture
def env(monkeypatch):
    s = SDK()
    root = ModuleType("pylablib")
    dev = ModuleType("pylablib.devices")
    th = ModuleType("Thorlabs")
    th.list_kinesis_devices = s.list
    th.KinesisMotor = s.motor
    dev.Thorlabs = th
    monkeypatch.setitem(sys.modules, "pylablib", root)
    monkeypatch.setitem(sys.modules, "pylablib.devices", dev)
    p = Path(__file__).parents[1] / "src/labtools/devices/kinesis_rotation_stage.py"
    sp = importlib.util.spec_from_file_location("_k", p)
    m = importlib.util.module_from_spec(sp)
    monkeypatch.setitem(sys.modules, sp.name, m)
    sp.loader.exec_module(m)
    return m, s


@pytest.mark.parametrize("v", [float("nan"), float("inf"), 0, -1])
def test_timeout_preflight(v, env):
    m, s = env
    with pytest.raises(ValueError):
        m.KinesisRotationStage(move_timeout_s=v)
    assert not s.events


@pytest.mark.parametrize("n", [0, 2])
def test_exactly_one(n, env):
    m, s = env
    s.devices = [(str(i), "x") for i in range(n)]
    with pytest.raises(m.KinesisRotationStageError):
        m.KinesisRotationStage().__enter__()


def test_success_native_order_and_thread(env):
    m, s = env
    d = m.KinesisRotationStage(move_timeout_s=3)
    d.connect()
    assert d.move_to(4.5) == 4.5
    d.stop()
    d.close()
    assert [x[0] for x in s.events] == [
        "list",
        "open",
        "move",
        "wait",
        "position",
        "stop",
        "close",
    ]
    assert {x[-1] for x in s.events} == {get_ident()}


@pytest.mark.parametrize("v", [float("nan"), float("inf"), -float("inf")])
def test_position_preflight_no_sdk(v, env):
    m, s = env
    d = m.KinesisRotationStage()
    d.connect()
    before = list(s.events)
    with pytest.raises(ValueError):
        d.move_to(v)
    assert s.events == before


@pytest.mark.parametrize("kind", [OSError, KeyboardInterrupt, asyncio.CancelledError])
def test_connect_primary_survives_cleanup(kind, env):
    m, s = env
    e = kind("open")
    s.fail["open"] = e
    with pytest.raises(kind) as c:
        m.KinesisRotationStage().__enter__()
    assert c.value is e


def test_failed_close_retains_uncertain_and_blocks(env):
    m, s = env
    d = m.KinesisRotationStage()
    d.connect()
    s.fail["close"] = OSError()
    with pytest.raises(m.KinesisRotationStageError):
        d.close()
    assert d._stage is s
    with pytest.raises(m.KinesisRotationStageError, match="teardown"):
        d.stop()


def test_no_wait_preserves_order(env):
    m, s = env
    d = m.KinesisRotationStage()
    d.connect()
    d.move_to(2, wait=False)
    assert "wait" not in [x[0] for x in s.events]
