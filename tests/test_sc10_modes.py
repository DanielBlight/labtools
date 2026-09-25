"""Hardware integration tests for the Thorlabs SC10 controller.

These tests communicate with a physical SC10. The controller output is
disabled before each test and remains disabled during cleanup.

Run explicitly with:

    uv run pytest tests/test_sc10_modes.py -m hardware -s
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from labtools.devices.sc10 import (
    SC10,
    SC10ExternalTriggerMode,
    SC10Mode,
    SC10TriggerMode,
)

pytestmark = pytest.mark.hardware


@pytest.fixture
def sc10() -> Iterator[SC10]:
    """Connect to the SC10 and restore its configuration after a test."""
    port = os.environ.get(
        "SC10_PORT",
        "COM4",
    )

    baud_rate = int(
        os.environ.get(
            "SC10_BAUD",
            "9600",
        )
    )

    with SC10(
        port=port,
        baud_rate=baud_rate,
    ) as shutter:
        original = shutter.get_state()

        shutter.set_enabled(False)

        try:
            yield shutter

        finally:
            shutter.set_enabled(False)
            shutter.set_mode(original.mode)
            shutter.set_trigger_mode(original.trigger_mode)
            shutter.set_external_trigger_mode(original.external_trigger_mode)
            shutter.set_open_time_ms(original.open_time_ms)
            shutter.set_close_time_ms(original.close_time_ms)
            shutter.set_repeat_count(original.repeat_count)


def test_sc10_identity(
    sc10: SC10,
) -> None:
    """Confirm that the connected instrument identifies as an SC10."""
    identity = sc10.identify()

    assert "SC10" in identity.upper()


@pytest.mark.parametrize(
    "mode",
    list(SC10Mode),
)
def test_sc10_mode_readback(
    sc10: SC10,
    mode: SC10Mode,
) -> None:
    """Set and verify each supported operating mode."""
    sc10.set_mode(mode)

    assert sc10.get_mode() == mode


@pytest.mark.parametrize(
    ("open_time_ms", "close_time_ms"),
    [
        (10, 20),
        (50, 60),
        (100, 110),
    ],
)
def test_sc10_timing_readback(
    sc10: SC10,
    open_time_ms: int,
    close_time_ms: int,
) -> None:
    """Set and verify programmed opening and closing times."""
    sc10.set_open_time_ms(open_time_ms)
    sc10.set_close_time_ms(close_time_ms)

    assert sc10.get_open_time_ms() == open_time_ms

    assert sc10.get_close_time_ms() == close_time_ms


@pytest.mark.parametrize(
    "repeat_count",
    [
        1,
        4,
        8,
    ],
)
def test_sc10_repeat_count_readback(
    sc10: SC10,
    repeat_count: int,
) -> None:
    """Set and verify representative repeat-count values."""
    sc10.set_repeat_count(repeat_count)

    assert sc10.get_repeat_count() == repeat_count


@pytest.mark.parametrize(
    "trigger_mode",
    list(SC10TriggerMode),
)
def test_sc10_trigger_mode_readback(
    sc10: SC10,
    trigger_mode: SC10TriggerMode,
) -> None:
    """Set and verify each trigger-input mode."""
    sc10.set_trigger_mode(trigger_mode)

    assert sc10.get_trigger_mode() == trigger_mode


@pytest.mark.parametrize(
    "output_mode",
    list(SC10ExternalTriggerMode),
)
def test_sc10_external_trigger_readback(
    sc10: SC10,
    output_mode: SC10ExternalTriggerMode,
) -> None:
    """Set and verify each external-trigger output mode."""
    sc10.set_external_trigger_mode(output_mode)

    assert sc10.get_external_trigger_mode() == output_mode
