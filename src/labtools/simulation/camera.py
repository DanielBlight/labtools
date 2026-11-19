"""Explicit synthetic camera source for development. Never imports native devices."""

import math
import time
from threading import Lock, get_ident

import numpy as np


class SimulatedIllumination:
    def __init__(self):
        self._lock = Lock()
        self._dark = False

    def set_dark(self, value):
        with self._lock:
            self._dark = bool(value)

    def is_dark(self):
        with self._lock:
            return self._dark


class SimulatedCamera:
    """UC480-wrapper-shaped source; deterministic noise, moving spots, fixed pattern.

    Raw synthetic monochrome uint8, 640x480. Exposure/gain affect signal and dark
    offset. Dark scene blocks only synthetic illumination, not physical hardware.
    """

    def __init__(self, *, exposure_s=.02, illumination=None, seed=0, stop_event=None):
        self.illumination = illumination if illumination is not None else SimulatedIllumination()
        self._stop = stop_event
        self._owner = get_ident()
        self._open = True
        self._live = False
        self._rng = np.random.default_rng(seed)
        self._sequence = 0
        self._next = time.monotonic()
        self._x = np.arange(640, dtype=np.float32)[None, :]
        self._y = np.arange(480, dtype=np.float32)[:, None]
        self._fixed = self._rng.uniform(0, 5, (480, 640)).astype(np.float32)
        self._gain = 1.
        self.set_exposure(exposure_s)

    def _check(self):
        if not self._open or get_ident() != self._owner:
            raise RuntimeError("Synthetic camera used outside its operation thread/lifetime")

    def get_max_gains(self):
        self._check()
        return (16.,)

    def set_master_gain(self, gain):
        self._check()
        if not math.isfinite(gain) or not 1 <= gain <= 16:
            raise ValueError("Synthetic gain must be 1..16")
        self._gain = float(gain)
        return self._gain

    def set_exposure(self, exposure):
        self._check()
        if not math.isfinite(exposure) or not .00001 <= exposure <= 10:
            raise ValueError("Synthetic exposure outside 0.01..10000 ms")
        self._exposure = float(exposure)
        return self._exposure

    def get_exposure(self):
        self._check()
        return self._exposure

    def get_device_info(self):
        self._check()
        return "SIMULATED CAMERA - synthetic 640x480 uint8; no physical device"

    def start_live(self, *, buffer_frames=3):
        self._check()
        self._live = True
        self._next = time.monotonic()

    def read_latest(self, *, timeout_s=1.):
        self._check()
        if not self._live:
            raise RuntimeError("Synthetic acquisition is not running")
        interval = max(1 / 30, self._exposure)
        wait = max(0., self._next - time.monotonic())
        if wait > timeout_s:
            raise TimeoutError("Synthetic frame wait exceeded timeout")
        if wait:
            if self._stop is not None:
                if self._stop.wait(wait):
                    return np.zeros((480, 640), dtype=np.uint8)
            else:
                time.sleep(wait)
        self._next = time.monotonic() + interval
        self._sequence += 1
        offset = 8 + self._fixed * self._gain + self._exposure * 10
        values = offset + self._rng.normal(0, .7, (480, 640))
        if not self.illumination.is_dark():
            phase = self._sequence * .025
            cx, cy = 320 + 80 * math.sin(phase), 240 + 45 * math.cos(phase)
            spot = np.exp(-((self._x - cx) ** 2 + (self._y - cy) ** 2) / (2 * 30 ** 2))
            reference = np.exp(-((self._x - 160) ** 2 + (self._y - 140) ** 2) / (2 * 16 ** 2))
            values = values + (spot * 150 + reference * 65) * (self._exposure / .02) * self._gain
        return np.clip(values, 0, 255).astype(np.uint8)

    def close(self):
        self._check()
        self._live = False
        self._open = False

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *args):
        self.close()
