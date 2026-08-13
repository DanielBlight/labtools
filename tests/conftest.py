"""Shared pytest fixtures/helpers for hardware-dependent smoke tests."""

from __future__ import annotations

import socket

import pytest

TC_ADDRESS = "169.254.99.159"
TC_SCPI_PORT = 5555


def time_controller_available(address: str = TC_ADDRESS, port: int = TC_SCPI_PORT) -> bool:
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
