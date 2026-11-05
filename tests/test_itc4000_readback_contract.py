"""Characterize current readbacks without changing production behavior."""

import asyncio
import math

import pytest
from test_itc4000_lifecycle import (
    wrapper as wrapper,  # noqa: PLC0414 - pytest fixture re-export
)

CURRENT_TRANSCRIPT = [
    ("write", "SOUR:CURR 0.05"),
    ("query", "*OPC?"),
    ("query", "SYST:ERR?"),
    ("query", "SOUR:CURR?"),
]


@pytest.mark.parametrize("reply", ["NaN", "-nan", "  nan  "])
def test_nan_reply_is_currently_accepted_without_extra_commands(wrapper, reply):
    cls, fake = wrapper
    with cls() as device:
        fake.responses["SOUR:CURR?"] = reply
        fake.events.clear()
        assert device.set_current(0.05) is None
        assert fake.events == CURRENT_TRANSCRIPT
        assert device.threshold_current == 0.049
        assert device.max_current == 0.1


@pytest.mark.parametrize("reply", ["-inf", "+Infinity", "-Infinity", "1e309", "-1e309"])
def test_other_infinite_forms_raise_existing_mismatch(wrapper, reply):
    cls, fake = wrapper
    with cls() as device:
        fake.responses["SOUR:CURR?"] = reply
        fake.events.clear()
        with pytest.raises(RuntimeError, match="Current readback mismatch") as caught:
            device.set_current(0.05)
        assert "requested 0.05 A" in str(caught.value)
        assert "inf A" in str(caught.value)
        assert fake.events == CURRENT_TRANSCRIPT


@pytest.mark.parametrize("reply", ["0.05", "  +5e-2\r\n", "0.0500000"])
def test_finite_matching_reply_preserves_success_transcript(wrapper, reply):
    cls, fake = wrapper
    with cls() as device:
        fake.responses["SOUR:CURR?"] = reply
        fake.events.clear()
        device.set_current(0.05)
        assert fake.events == CURRENT_TRANSCRIPT


@pytest.mark.parametrize("requested", [0.0, 0.05])
@pytest.mark.parametrize("direction", [-1, 1])
@pytest.mark.parametrize("outside", [False, True])
def test_absolute_and_relative_tolerance_neighbors(wrapper, requested, direction, outside):
    cls, fake = wrapper
    tolerance = max(1e-6, abs(requested) * 1e-4)
    boundary = requested + direction * tolerance
    readback = math.nextafter(boundary, direction * math.inf if outside else requested)
    assert (abs(readback - requested) > tolerance) is outside
    with cls() as device:
        fake.responses["SOUR:CURR?"] = repr(readback)
        fake.events.clear()
        if outside:
            with pytest.raises(RuntimeError, match="Current readback mismatch"):
                device.set_current(requested)
        else:
            device.set_current(requested)
        assert fake.events == [
            ("write", f"SOUR:CURR {requested:.9g}"),
            ("query", "*OPC?"), ("query", "SYST:ERR?"),
            ("query", "SOUR:CURR?"),
        ]


@pytest.mark.parametrize("reply", ["", "   ", "not-a-number", "0.05 A"])
def test_malformed_reply_raises_conversion_valueerror_after_write(wrapper, reply):
    cls, fake = wrapper
    with cls() as device:
        fake.responses["SOUR:CURR?"] = reply
        fake.events.clear()
        with pytest.raises(ValueError):
            device.set_current(0.05)
        assert fake.events == CURRENT_TRANSCRIPT


@pytest.mark.parametrize("reply", [None, 0.05])
def test_nontext_transport_reply_fails_at_strip_not_float(wrapper, reply):
    cls, fake = wrapper
    with cls() as device:
        fake.responses["SOUR:CURR?"] = reply
        fake.events.clear()
        with pytest.raises(AttributeError, match="strip"):
            device.set_current(0.05)
        assert fake.events == CURRENT_TRANSCRIPT


@pytest.mark.parametrize("kind", [ValueError, TypeError])
def test_float_conversion_exception_identity_is_preserved(wrapper, kind):
    cls, fake = wrapper
    error = kind("readback conversion sentinel")

    class Converted:
        def __float__(self):
            raise error

    class Reply:
        def strip(self):
            return Converted()

    with cls() as device:
        fake.responses["SOUR:CURR?"] = Reply()
        fake.events.clear()
        with pytest.raises(kind) as caught:
            device.set_current(0.05)
        assert caught.value is error
        assert fake.events == CURRENT_TRANSCRIPT


@pytest.mark.parametrize("reply", ["nan", "inf", "-inf", " 0.05 "])
def test_direct_getter_remains_raw_float_conversion(wrapper, reply):
    cls, fake = wrapper
    with cls() as device:
        fake.responses["SOUR:CURR?"] = reply
        fake.events.clear()
        value = device.get_current()
        expected = float(reply)
        assert math.isnan(value) if math.isnan(expected) else value == expected
        assert fake.events == [("query", "SOUR:CURR?")]


@pytest.mark.parametrize("kind", [OSError, TimeoutError, KeyboardInterrupt, asyncio.CancelledError])
def test_query_exception_identity_and_context_cleanup(wrapper, kind):
    cls, fake = wrapper
    error = kind("readback query sentinel")
    device = cls()
    fake.failures[("query", "SOUR:CURR?")] = error
    fake.events.clear()
    with pytest.raises(kind) as caught, device:
        device.set_current(0.05)
    assert caught.value is error
    assert fake.events == [*CURRENT_TRANSCRIPT, ("instrument-close",), ("manager-close",)]
    assert device._closed
    assert not hasattr(error, "_itc4000_cleanup_failures")


@pytest.mark.parametrize("reply", ["-inf", "0.09", "invalid"])
def test_readback_failure_remains_primary_when_both_closes_fail(wrapper, reply):
    cls, fake = wrapper
    device = cls()
    fake.responses["SOUR:CURR?"] = reply
    instrument_error = OSError("instrument close sentinel")
    manager_error = OSError("manager close sentinel")
    fake.failures["instrument-close"] = instrument_error
    fake.failures["manager-close"] = manager_error
    fake.events.clear()
    expected_kind = ValueError if reply == "invalid" else RuntimeError
    primary = None
    try:
        with pytest.raises(expected_kind) as caught, device:
            try:
                device.set_current(0.05)
            except expected_kind as error:
                primary = error
                raise
        assert caught.value is primary
        cleanup_failures = primary._itc4000_cleanup_failures
        assert len(cleanup_failures) == 1
        cleanup = cleanup_failures[0]
        assert isinstance(cleanup, ExceptionGroup)
        assert cleanup.exceptions == (instrument_error, manager_error)
        assert primary.__notes__
        assert fake.events == [*CURRENT_TRANSCRIPT, ("instrument-close",), ("manager-close",)]
        assert device._close_started and not device._closed
    finally:
        fake.failures.clear()
        device.close()
    assert device._closed
