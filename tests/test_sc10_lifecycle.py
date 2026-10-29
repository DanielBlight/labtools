import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


class Port:
    def __init__(self, o):
        self.o = o
        self.is_open = True

    def r(self, n, *a):
        self.o.ev.append((n, *a))
        e = self.o.fail.get(n)
        e is not None and (_ for _ in ()).throw(e)

    def reset_input_buffer(self):
        self.r("rin")

    def reset_output_buffer(self):
        self.r("rout")

    def write(self, b):
        self.r("write", b)

    def flush(self):
        self.r("flush")

    def read_until(self, p):
        self.r("read", p)
        return self.o.reply

    def cancel_read(self):
        self.r("cancel_read")

    def cancel_write(self):
        self.r("cancel_write")

    def close(self):
        self.r("close")
        self.is_open = False


class SDK:
    def __init__(self):
        self.ev = []
        self.fail = {}
        self.reply = b"id?\r\nSC10 Controller\r\n> "
        self.p = Port(self)

    def create(self, *a, **k):
        self.ev.append(("create", a, k))
        e = self.fail.get("create")
        e is not None and (_ for _ in ()).throw(e)
        return self.p


@pytest.fixture
def env(monkeypatch):
    s = SDK()
    serial = ModuleType("serial")
    serial.Serial = s.create
    serial.EIGHTBITS = 8
    serial.PARITY_NONE = "N"
    serial.STOPBITS_ONE = 1
    tools = ModuleType("serial.tools")
    lp = ModuleType("serial.tools.list_ports")
    lp.comports = list
    tools.list_ports = lp
    for n, m in [
        ("serial", serial),
        ("serial.tools", tools),
        ("serial.tools.list_ports", lp),
    ]:
        monkeypatch.setitem(sys.modules, n, m)
    src = Path(__file__).parents[1] / "src/labtools/devices/sc10.py"
    sp = importlib.util.spec_from_file_location("_sc10", src)
    m = importlib.util.module_from_spec(sp)
    monkeypatch.setitem(sys.modules, sp.name, m)
    sp.loader.exec_module(m)
    return m, s


def test_open_identify_transcript(env):
    m, s = env
    d = m.SC10(auto_connect=True)
    assert s.ev[1:] == [
        ("rin",),
        ("rout",),
        ("rin",),
        ("write", b"id?\r"),
        ("flush",),
        ("read", b"> "),
    ]
    d.close()
    assert not d.is_connected


@pytest.mark.parametrize("reply", [b"", b"id? \r\n   SC10   Controller \r\n>   "])
def test_timeout_and_whitespace(env, reply):
    m, s = env
    s.reply = reply
    d = m.SC10()
    if not reply:
        with pytest.raises(TimeoutError):
            d.connect()
    else:
        d.connect()
        assert d.identify() == "SC10 Controller"


def test_wrong_device_closes(env):
    m, s = env
    s.reply = b"id?\r\nOTHER\r\n> "
    with pytest.raises(m.SC10Error):
        m.SC10(auto_connect=True)
    assert ("close",) in s.ev


@pytest.mark.parametrize("kind", [OSError, KeyboardInterrupt, asyncio.CancelledError])
def test_primary_survives_close_failure(env, kind):
    m, s = env
    primary = kind("identify")
    s.fail.update(read=primary, close=OSError("close"))
    with pytest.raises(kind) as c:
        m.SC10(auto_connect=True)
    assert c.value is primary and primary._sc10_cleanup_failures


def test_close_failure_retains_handle_and_blocks_commands(env):
    m, s = env
    d = m.SC10(auto_connect=True)
    s.fail["close"] = OSError("close")
    with pytest.raises(m.SC10Error):
        d.close()
    assert d._serial is s.p
    with pytest.raises(m.SC10Error, match="teardown"):
        d.identify()


def test_query_command_and_no_toggle_retry(env):
    m, s = env
    d = m.SC10(auto_connect=True)
    s.ev.clear()
    s.reply = b"ens?\r\n0\r\n> "
    assert not d.is_enabled()
    assert s.ev[1] == ("write", b"ens?\r")
    s.reply = b"error\r\n> "
    with pytest.raises(m.SC10Error):
        d.toggle_enable()
    assert sum(e[0] == "write" for e in s.ev) == 2


def test_parameter_validation_before_open(env):
    m, s = env
    with pytest.raises(ValueError):
        m.SC10(baud_rate=0, auto_connect=True)
    with pytest.raises(ValueError):
        m.SC10(timeout_s=0, auto_connect=True)
    assert s.ev == []
