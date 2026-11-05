"""Current behavior only: fake VISA, no new validation policy."""

import math

import pytest
from test_itc4000_lifecycle import (
    wrapper as wrapper,  # noqa: PLC0414 - pytest fixture re-export
)


@pytest.mark.parametrize(
    ("threshold", "maximum", "accepted"),
    [
        (0, 0.1, True), (0.1, 0.1, True), ("0.049", "0.1", True),
        (-1, 0.1, False), (0, 0, False), (0.2, 0.1, False),
        (float("nan"), 0.1, True), (0.049, float("nan"), True),
        (float("inf"), float("inf"), True), (0.049, float("inf"), True),
        (float("inf"), 0.1, False), (float("-inf"), 0.1, False),
        (0.049, float("-inf"), False), (False, True, True),
    ],
)
def test_constructor_current_policy(wrapper, threshold, maximum, accepted):
    cls, fake = wrapper
    if not accepted:
        with pytest.raises(ValueError):
            cls(threshold_current=threshold, max_current=maximum)
        assert fake.events == []
        return
    with cls(threshold_current=threshold, max_current=maximum) as device:
        assert fake.events[0] == ("manager-create",)
        assert isinstance(device.threshold_current, float)
        assert isinstance(device.max_current, float)
        assert not any(e[0] == "write" and "CURR" in e[1] for e in fake.events)


@pytest.mark.parametrize(("value", "kind"), [("bad", ValueError), (None, TypeError)])
@pytest.mark.parametrize("field", ["threshold_current", "max_current"])
def test_constructor_conversion_failure_precedes_open(wrapper, value, kind, field):
    cls, fake = wrapper
    with pytest.raises(kind):
        cls(**{field: value})
    assert fake.events == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -0.001, 0.101])
def test_current_rejected_before_transport_with_finite_ceiling(wrapper, value):
    cls, fake = wrapper
    with cls() as device:
        fake.events.clear()
        with pytest.raises(ValueError):
            device.set_current(value)
        assert fake.events == []


@pytest.mark.parametrize("value", [0, 0.1, "0.05", False])
def test_current_bounds_conversion_transcript_and_no_cache(wrapper, value):
    cls, fake = wrapper
    with cls() as device:
        current = float(value)
        fake.responses["SOUR:CURR?"] = str(current)
        fake.events.clear()
        device.set_current(value)
        assert fake.events == [
            ("write", f"SOUR:CURR {current:.9g}"),
            ("query", "*OPC?"), ("query", "SYST:ERR?"),
            ("query", "SOUR:CURR?"),
        ]
        assert device.threshold_current == 0.049
        assert device.max_current == 0.1


def test_nan_ceiling_rejects_even_finite_current(wrapper):
    cls, fake = wrapper
    with cls(max_current=float("nan")) as device:
        fake.events.clear()
        with pytest.raises(ValueError):
            device.set_current(0.05)
        assert fake.events == []


def test_infinite_ceiling_permits_infinite_current(wrapper):
    cls, fake = wrapper
    with cls(max_current=float("inf")) as device:
        fake.responses["SOUR:CURR?"] = "inf"
        fake.events.clear()
        device.set_current(float("inf"))
        assert fake.events[0] == ("write", "SOUR:CURR inf")
        assert fake.events[-1] == ("query", "SOUR:CURR?")


@pytest.mark.parametrize("readback", ["nan", "inf", "0.09"])
def test_readback_comparison_current_behavior(wrapper, readback):
    cls, fake = wrapper
    with cls() as device:
        fake.responses["SOUR:CURR?"] = readback
        if readback == "nan":
            device.set_current(0.05)
        else:
            with pytest.raises(RuntimeError, match="readback mismatch"):
                device.set_current(0.05)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "20.5", -1000, True])
def test_temperature_formats_without_finite_or_range_check(wrapper, value):
    cls, fake = wrapper
    with cls() as device:
        fake.events.clear()
        device.set_temperature(value)
        assert fake.events == [
            ("write", f"SOUR2:TEMP {float(value):.9g}C"),
            ("query", "*OPC?"), ("query", "SYST:ERR?"),
        ]


@pytest.mark.parametrize("method", ["set_current", "set_temperature"])
@pytest.mark.parametrize(("value", "kind"), [("bad", ValueError), (None, TypeError)])
def test_setter_conversion_failure_no_transport(wrapper, method, value, kind):
    cls, fake = wrapper
    with cls() as device:
        fake.events.clear()
        with pytest.raises(kind):
            getattr(device, method)(value)
        assert fake.events == []


@pytest.mark.parametrize("delay", [float("nan"), float("inf"), float("-inf"), -1, "1"])
def test_enable_delay_order_without_sleep_or_outputs(wrapper, monkeypatch, delay):
    cls, _fake = wrapper
    calls = []
    monkeypatch.setattr(cls.enable.__globals__["time"], "sleep", calls.append)
    with cls() as device:
        monkeypatch.setattr(device, "get_tec_output", lambda: calls.append("read-tec") or False)
        monkeypatch.setattr(device, "enable_tec", lambda: calls.append("enable-tec"))
        monkeypatch.setattr(device, "set_current", lambda value: calls.append(("current", value)))
        monkeypatch.setattr(device, "enable_diode", lambda: calls.append("enable-diode"))
        if isinstance(delay, str):
            with pytest.raises(TypeError):
                device.enable(0.05, delay)
            assert calls == []
        elif delay < 0:
            with pytest.raises(ValueError):
                device.enable(0.05, delay)
            assert calls == []
        else:
            device.enable(0.05, delay)
            assert calls[:2] == ["read-tec", "enable-tec"]
            assert math.isnan(calls[2]) if math.isnan(delay) else calls[2] == delay
            assert calls[3:] == [("current", 0.05), "enable-diode"]


def test_enable_invalid_current_checks_after_tec_work(wrapper, monkeypatch):
    cls, fake = wrapper
    calls = []
    monkeypatch.setattr(cls.enable.__globals__["time"], "sleep", calls.append)
    with cls() as device:
        monkeypatch.setattr(device, "get_tec_output", lambda: calls.append("read-tec") or False)
        monkeypatch.setattr(device, "enable_tec", lambda: calls.append("enable-tec"))
        fake.events.clear()
        with pytest.raises(ValueError):
            device.enable(float("nan"), 0)
        assert calls == ["read-tec", "enable-tec", 0]
        assert fake.events == []


@pytest.mark.parametrize("timeout", [0, -1, "1234", float("nan"), float("inf")])
def test_timeout_is_forwarded_not_validated(wrapper, timeout):
    cls, fake = wrapper
    with cls(timeout_ms=timeout):
        assert fake.events[1][0:2] == ("open", cls.DEFAULT_ADDRESS)
        assert fake.events[1][2] is timeout
