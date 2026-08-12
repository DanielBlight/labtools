import socket

import numpy as np
import pytest

from labtools.devices.idq_time_controller import IDQTimeController

TC_ADDRESS = "169.254.99.159"
THRESHOLD_V = 0.1
HIST_STOP_CHANNEL = 2
HIST_REF_CHANNEL = 4


def _time_controller_available(address: str = TC_ADDRESS, port: int = 5555) -> bool:
    sock = socket.socket()
    sock.settimeout(1)
    try:
        sock.connect((address, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _device_for_smoke_test():
    if not _time_controller_available():
        pytest.skip(f"Time Controller not reachable at {TC_ADDRESS}:{5555}")
    return IDQTimeController(TC_ADDRESS)


def test_get_counts_smoke():
    with _device_for_smoke_test() as tc:
        tc.configure_channel(2, threshold_v=THRESHOLD_V, edge="rising")
        counts = tc.get_counts(channel=2, duration_s=0.5)

        assert isinstance(counts, int)
        assert counts >= 0


def test_get_histogram_smoke():
    with _device_for_smoke_test() as tc:
        tc.configure_channel(2, threshold_v=THRESHOLD_V, edge="rising")
        tc.configure_channel(4, threshold_v=THRESHOLD_V, edge="rising")
        tc.configure_histogram(
            hist=1,
            stop_channel=HIST_STOP_CHANNEL,
            ref_channel=HIST_REF_CHANNEL,
            bin_width_ps=1000,
            bin_count=1024,
        )

        x_ps, y = tc.get_histogram(hist=1, duration_s=0.5)

        assert isinstance(x_ps, np.ndarray)
        assert isinstance(y, np.ndarray)
        assert x_ps.shape == y.shape
        assert x_ps.size > 0
        assert np.all(y >= 0)
        assert np.all(np.diff(x_ps) > 0)
