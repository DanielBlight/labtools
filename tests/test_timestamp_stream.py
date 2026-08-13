"""Vendor-style timestamp streaming smoke test.

This mirrors the vendor example flow more closely than a plain wall-time sleep:
- configure the input channels
- start the DLT stream for each channel
- arm and play a timed record
- wait for the acquisition to complete and the DLT to go idle
- then stop the stream cleanly and inspect the received timestamps
"""

import numpy as np

from labtools.devices.idq_time_controller import IDQTimeController

STREAM_DURATION_S = 3
CHANNELS = [2, 4]
THRESHOLD_V = 0.1
MIN_DATA_SPAN_S = 0.5


def _summarise_channel(chunks: list[np.ndarray]) -> tuple[int, float]:
    if not chunks:
        return 0, 0.0
    all_ts = np.concatenate(chunks)
    total = int(len(all_ts))
    if total < 2:
        span_s = 0.0
    else:
        span_s = float((all_ts.max() - all_ts.min()) / 1e12)
    return total, span_s


def test_timestamp_stream_lifecycle_smoke(time_controller_address):
    received: dict[int, list[np.ndarray]] = {ch: [] for ch in CHANNELS}

    def on_chunk(channel: int, timestamps_ps: np.ndarray):
        received[channel].append(timestamps_ps)

    with IDQTimeController(time_controller_address) as tc:
        for ch in CHANNELS:
            tc.configure_channel(ch, threshold_v=THRESHOLD_V, edge="rising")

        tc.acquire_timestamp_stream(
            channels=CHANNELS,
            callback=on_chunk,
            duration_s=STREAM_DURATION_S,
            timeout_s=30
        )

    summary = {}
    for ch in CHANNELS:
        total, span_s = _summarise_channel(received[ch])
        summary[ch] = {"total": total, "span_s": span_s}
        print(
            f"Channel {ch}: total timestamps={total}, global span={span_s:.3f}s, "
            f"chunks={len(received[ch])}"
        )
        assert total > 0, f"No timestamps received on channel {ch}"
        assert span_s > MIN_DATA_SPAN_S, (
            f"Timestamp span too short on channel {ch}: {span_s:.3f}s "
            f"(threshold={MIN_DATA_SPAN_S:.3f}s)"
        )

    assert all(summary[ch]["total"] > 0 for ch in CHANNELS)
    assert all(summary[ch]["span_s"] > MIN_DATA_SPAN_S for ch in CHANNELS)
