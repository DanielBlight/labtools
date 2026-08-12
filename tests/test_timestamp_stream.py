"""Simple test script for IDQTimeController timestamp streaming.

Connects to the Time Controller, configures channels 1 and 4, streams
timestamps for a fixed duration, then prints a summary of what was received.

Run with:
    python tests/test_timestamp_stream.py
"""

import time
import threading
import numpy as np
from labtools.devices.idq_time_controller import IDQTimeController

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

TC_ADDRESS = "169.254.99.159"
STREAM_DURATION_S = 5.0
CHANNELS = [2, 4]
THRESHOLD_V = 0.1

# ------------------------------------------------------------------
# Callback and accumulator
# ------------------------------------------------------------------

received: dict[int, list[np.ndarray]] = {ch: [] for ch in CHANNELS}
lock = threading.Lock()


def on_chunk(channel: int, timestamps_ps: np.ndarray):
    with lock:
        received[channel].append(timestamps_ps)
    print(f"  [ch{channel}] chunk: {len(timestamps_ps)} timestamps")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    with IDQTimeController(TC_ADDRESS) as tc:
        print(f"Connected to Time Controller at {TC_ADDRESS}\n")

        for ch in CHANNELS:
            tc.configure_channel(ch, threshold_v=THRESHOLD_V, edge="rising")
            print(f"Channel {ch} configured: threshold={THRESHOLD_V}V, edge=rising")

        print(f"\nStarting timestamp stream on channels {CHANNELS} "
              f"for {STREAM_DURATION_S}s ...\n")

        tc.start_timestamp_stream(channels=CHANNELS, callback=on_chunk)
        time.sleep(STREAM_DURATION_S)
        tc.stop_timestamp_stream()

        print("\n--- Summary ---")
        for ch in CHANNELS:
            chunks = received[ch]
            total = sum(len(c) for c in chunks)
            if total > 0:
                all_ts = np.concatenate(chunks)
                duration_s = (all_ts[-1] - all_ts[0]) / 1e12
                rate = total / duration_s if duration_s > 0 else 0.0
                print(
                    f"Channel {ch}: {total} timestamps in {len(chunks)} chunks "
                    f"| span={duration_s:.3f}s | rate≈{rate:.0f} counts/s"
                )
            else:
                print(f"Channel {ch}: no timestamps received")


if __name__ == "__main__":
    main()
