"""Whole-wrapper tests with isolated fake PyVISA modules; no native VISA access."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from threading import get_ident
from types import ModuleType

import pytest


class FakeVisa:
    def __init__(self):
        self.events = []
        self.threads = []
        self.failures = {}
        self.responses = {
            "*IDN?": "FAKE ITC4000",
            "*OPC?": "1",
            "SYST:ERR?": '0,"No error"',
            "SOUR:CURR?": "0.05",
            "OUTP?": "0",
            "OUTP2?": "0",
        }
        owner = self

        class Instrument:
            def __setattr__(self, name, value):
                if name in {"write_termination", "read_termination"}:
                    owner.record(name, value)
                object.__setattr__(self, name, value)

            def write(self, command):
                owner.record("write", command)

            def query(self, command):
                owner.record("query", command)
                return owner.responses[command]

            def close(self):
                owner.record("instrument-close")

        class Manager:
            def open_resource(self, address, *, timeout):
                owner.record("open", address, timeout)
                return owner.instrument

            def close(self):
                owner.record("manager-close")

        self.instrument = Instrument()
        self.manager = Manager()

    def record(self, name, *args):
        self.events.append((name, *args))
        self.threads.append(get_ident())
        error = self.failures.get((name, *args), self.failures.get(name))
        if error is not None:
            raise error

    def factory(self):
        self.record("manager-create")
        return self.manager


@pytest.fixture
def wrapper(monkeypatch):
    fake = FakeVisa()
    visa = ModuleType("pyvisa")
    visa.ResourceManager = fake.factory
    resources = ModuleType("pyvisa.resources")
    resources.MessageBasedResource = type(fake.instrument)
    monkeypatch.setitem(sys.modules, "pyvisa", visa)
    monkeypatch.setitem(sys.modules, "pyvisa.resources", resources)
    source = Path(__file__).parents[1] / "src/labtools/devices/itc4000.py"
    spec = importlib.util.spec_from_file_location("_itc4000_fake_lifecycle", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ITC4000, fake


def test_success_transcript_single_session_and_owner_thread(wrapper):
    cls, fake = wrapper
    with cls("FAKE", timeout_ms=1234) as device:
        assert device.identify() == "FAKE ITC4000"
        device.set_current(0.05)
        assert device.get_diode_output() is False
        assert device.get_tec_output() is False
    assert fake.events == [
        ("manager-create",),
        ("open", "FAKE", 1234),
        ("write_termination", "\n"),
        ("read_termination", "\n"),
        ("write", "*CLS"),
        ("query", "*IDN?"),
        ("write", "SOUR:CURR 0.05"),
        ("query", "*OPC?"),
        ("query", "SYST:ERR?"),
        ("query", "SOUR:CURR?"),
        ("query", "OUTP?"),
        ("query", "OUTP2?"),
        ("instrument-close",),
        ("manager-close",),
    ]
    assert set(fake.threads) == {get_ident()}
    device.close()
    assert fake.events[-2:] == [("instrument-close",), ("manager-close",)]
    assert device._closed and device._itc is None and device._rm is None
    before = list(fake.events)
    with pytest.raises(RuntimeError, match="closed"):
        device.identify()
    assert fake.events == before


@pytest.mark.parametrize(
    "stage",
    [
        "manager-create",
        "open",
        "write_termination",
        "read_termination",
        ("write", "*CLS"),
    ],
)
@pytest.mark.parametrize("kind", [OSError, KeyboardInterrupt, asyncio.CancelledError])
def test_startup_failure_closes_only_acquired_handles(wrapper, stage, kind):
    cls, fake = wrapper
    primary = kind("startup failed")
    fake.failures[stage] = primary
    with pytest.raises(kind) as caught:
        cls("FAKE")
    assert caught.value is primary
    closes = [event[0] for event in fake.events if event[0].endswith("-close")]
    expected = (
        []
        if stage == "manager-create"
        else ["manager-close"]
        if stage == "open"
        else ["instrument-close", "manager-close"]
    )
    assert closes == expected
    assert set(fake.threads) == {get_ident()}


@pytest.mark.parametrize(
    "instrument_fails,manager_fails", [(True, False), (False, True), (True, True)]
)
def test_close_retains_failures_and_only_explicitly_retries_failed_handles(
    wrapper, instrument_fails, manager_fails
):
    cls, fake = wrapper
    device = cls("FAKE")
    failures = []
    for stage, enabled in [
        ("instrument-close", instrument_fails),
        ("manager-close", manager_fails),
    ]:
        if enabled:
            error = OSError(stage)
            fake.failures[stage] = error
            failures.append(error)
    with pytest.raises(ExceptionGroup) as caught:
        device.close()
    assert list(caught.value.exceptions) == failures
    assert fake.events[-2:] == [("instrument-close",), ("manager-close",)]
    assert not device._closed
    assert (device._itc is fake.instrument) is instrument_fails
    assert (device._rm is fake.manager) is manager_fails
    before = list(fake.events)
    with pytest.raises(RuntimeError, match="teardown"):
        device.set_current(0.05)
    assert fake.events == before
    fake.failures.clear()
    device.close()
    retried = fake.events[len(before) :]
    assert retried == [
        (stage,)
        for stage, enabled in [
            ("instrument-close", instrument_fails),
            ("manager-close", manager_fails),
        ]
        if enabled
    ]
    assert device._closed
    device.close()
    assert fake.events[len(before) :] == retried


@pytest.mark.parametrize(
    "primary_kind", [OSError, KeyboardInterrupt, asyncio.CancelledError]
)
@pytest.mark.parametrize(
    "cleanup_kind", [OSError, KeyboardInterrupt, asyncio.CancelledError]
)
def test_startup_and_cleanup_preserve_primary_and_all_cleanup(
    wrapper, primary_kind, cleanup_kind
):
    cls, fake = wrapper
    primary = primary_kind("CLS failed")
    cleanup = cleanup_kind("instrument cleanup")
    other = OSError("manager cleanup")
    fake.failures.update(
        {
            ("write", "*CLS"): primary,
            "instrument-close": cleanup,
            "manager-close": other,
        }
    )
    with pytest.raises(primary_kind) as caught:
        cls("FAKE")
    assert caught.value is primary
    retained = primary._itc4000_cleanup_failures[0]
    if isinstance(cleanup, Exception):
        assert retained.exceptions == (cleanup, other)
    else:
        assert retained is cleanup
        assert cleanup._itc4000_cleanup_failures == (other,)
    assert "cleanup also failed" in primary.__notes__[0]
    assert fake.events[-2:] == [("instrument-close",), ("manager-close",)]


@pytest.mark.parametrize(
    "body_kind", [OSError, KeyboardInterrupt, asyncio.CancelledError]
)
@pytest.mark.parametrize(
    "cleanup_kind", [OSError, KeyboardInterrupt, asyncio.CancelledError]
)
def test_body_exception_survives_cleanup_failure(wrapper, body_kind, cleanup_kind):
    cls, fake = wrapper
    primary = body_kind("body failed")
    cleanup = cleanup_kind("close failed")
    fake.failures["instrument-close"] = cleanup
    with pytest.raises(body_kind) as caught, cls("FAKE"):
        raise primary
    assert caught.value is primary
    retained = primary._itc4000_cleanup_failures[0]
    if isinstance(cleanup, Exception):
        assert retained.exceptions == (cleanup,)
    else:
        assert retained is cleanup
    assert fake.events[-1] == ("manager-close",)


@pytest.mark.parametrize("kind", [KeyboardInterrupt, asyncio.CancelledError])
@pytest.mark.parametrize("stage", ["instrument-close", "manager-close"])
def test_cleanup_baseexception_is_not_an_ordinary_group_member(wrapper, kind, stage):
    cls, fake = wrapper
    device = cls("FAKE")
    primary = kind("interrupted cleanup")
    other_stage = "manager-close" if stage == "instrument-close" else "instrument-close"
    other = OSError("other close")
    fake.failures.update({stage: primary, other_stage: other})
    with pytest.raises(kind) as caught:
        device.close()
    assert caught.value is primary
    assert primary._itc4000_cleanup_failures == (other,)
    assert fake.events[-2:] == [("instrument-close",), ("manager-close",)]


def test_clean_context_body_failure_does_not_add_cleanup_notes(wrapper):
    cls, fake = wrapper
    primary = ValueError("body")
    with pytest.raises(ValueError) as caught, cls("FAKE"):
        raise primary
    assert caught.value is primary
    assert not hasattr(primary, "_itc4000_cleanup_failures")
    assert fake.events[-2:] == [("instrument-close",), ("manager-close",)]


def test_context_without_body_failure_raises_cleanup_group(wrapper):
    cls, fake = wrapper
    fake.failures["manager-close"] = OSError("manager close")
    with pytest.raises(ExceptionGroup) as caught, cls("FAKE"):
        pass
    assert caught.value.exceptions == (fake.failures["manager-close"],)


def test_startup_validation_and_defaults_are_unchanged(wrapper):
    cls, fake = wrapper
    with pytest.raises(ValueError, match="threshold_current"):
        cls(threshold_current=-1)
    assert fake.events == []
    device = cls()
    assert device.address == cls.DEFAULT_ADDRESS
    assert device.threshold_current == 0.049 and device.max_current == 0.100
    assert fake.events[1] == ("open", cls.DEFAULT_ADDRESS, 5000)
    device.close()
