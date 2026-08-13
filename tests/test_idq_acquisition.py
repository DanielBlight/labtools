import numpy as np

from labtools.devices.idq_time_controller import IDQTimeController

THRESHOLD_V = 0.1
HIST_STOP_CHANNEL = 2
HIST_REF_CHANNEL = 4


def test_get_counts_smoke(time_controller_address):
    with IDQTimeController(time_controller_address) as tc:
        tc.configure_channel(2, threshold_v=THRESHOLD_V, edge="rising")
        counts = tc.get_counts(channel=2, duration_s=0.5)

        assert isinstance(counts, int)
        assert counts >= 0


def test_get_histogram_smoke(time_controller_address):
    with IDQTimeController(time_controller_address) as tc:
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
