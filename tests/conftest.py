"""Shared pytest fixtures/helpers for hardware-dependent smoke tests."""

from __future__ import annotations

import socket

import pytest

TC_ADDRESS = "169.254.99.159"
TC_SCPI_PORT = 5555


def time_controller_available(
    address: str = TC_ADDRESS, port: int = TC_SCPI_PORT
) -> bool:
    """Return True if a TCP connection to the Time Controller's SCPI port succeeds."""
    sock = socket.socket()
    sock.settimeout(1)
    try:
        sock.connect((address, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


@pytest.fixture
def time_controller_address() -> str:
    """Return the configured Time Controller address, skipping the test if unreachable."""
    if not time_controller_available():
        pytest.skip(f"Time Controller not reachable at {TC_ADDRESS}:{TC_SCPI_PORT}")
    return TC_ADDRESS


# labtools hardware opt-in v3


def pytest_addoption(parser):
    """Register explicit hardware permission."""
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="Allow marked laboratory hardware tests to execute",
    )


def pytest_collection_modifyitems(config, items):
    """Mark known device tests and require explicit permission to execute."""
    known = {
        "test_idq_acquisition.py",
        "test_sc10_modes.py",
        "test_timestamp_stream.py",
    }
    for item in items:
        if item.path.name in known or "time_controller_address" in item.fixturenames:
            if item.get_closest_marker("hardware") is None:
                item.add_marker(pytest.mark.hardware)
        if item.get_closest_marker("hardware") and not config.getoption(
            "--run-hardware"
        ):
            item.add_marker(pytest.mark.skip(reason="Requires --run-hardware"))


def pytest_ignore_collect(collection_path, config):
    """Exclude known hardware modules before their native imports execute."""
    hardware_modules = {
        "test_idq_acquisition.py",
        "test_sc10_modes.py",
        "test_timestamp_stream.py",
    }
    if collection_path.name in hardware_modules and not config.getoption(
        "--run-hardware"
    ):
        return True
    return None
