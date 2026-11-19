"""Bounded latest-frame preview and raw-domain dark subtraction, without Qt/SDKs."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from threading import Lock

import numpy as np


@dataclass(frozen=True)
class CameraContext:
    exposure_s: float
    gain: float
    device: str


@dataclass(frozen=True)
class PreviewFrame:
    pixels: np.ndarray
    sequence: int
    acquired_at: float
    raw_shape: tuple
    raw_dtype: str
    dark_status: str
    corrected: bool


class LatestPreview:
    """A one-slot mailbox: slow display drops old previews, never queues frames."""

    def __init__(self):
        self._lock = Lock()
        self._frame = None
        self.replaced = 0

    def put(self, frame):
        with self._lock:
            self.replaced += self._frame is not None
            self._frame = frame

    def take(self):
        with self._lock:
            frame, self._frame = self._frame, None
            return frame


def raw_frame(frame):
    array = np.asarray(frame)
    if array.dtype not in (np.dtype("uint8"), np.dtype("uint16")):
        raise ValueError("Preview requires raw uint8 or uint16 camera samples")
    if array.ndim == 3 and array.shape[2] == 4:
        array = array[..., :3]  # Ignore alpha; camera-native colour is BGR.
    if array.ndim != 2 and not (array.ndim == 3 and array.shape[2] == 3):
        raise ValueError("Expected monochrome HxW or camera-native BGR HxWx3")
    if not array.size or min(array.shape[:2]) < 1:
        raise ValueError("Empty camera image")
    return array


class PreviewProcessor:
    """Dark is raw, full-resolution and independent of display scaling/decimation.

    No shutter commands. Imported images have unverified acquisition settings unless
    loaded from our metadata-bearing NPZ. Capture dark takes the next complete frame.
    """

    def __init__(self):
        self._lock = Lock()
        self._dark = None
        self._context = None
        self._origin = "none"
        self._capture = False
        self._enabled = False
        self._sequence = 0
        self._size = (1280, 960)
        self._white = 65535

    def set_size(self, width, height):
        with self._lock:
            self._size = (max(1, min(int(width), 1920)), max(1, min(int(height), 1440)))

    def set_white(self, value):
        if type(value) not in (int, float) or not math.isfinite(value) or not 1 <= value <= 65535:
            raise ValueError("16-bit preview white level must be 1..65535")
        with self._lock:
            self._white = int(value)

    def enable(self, enabled):
        with self._lock:
            self._enabled = bool(enabled)

    def capture_dark(self):
        with self._lock:
            self._capture = True

    def cancel_capture(self):
        with self._lock:
            self._capture = False

    def clear_dark(self):
        with self._lock:
            self._dark = self._context = None
            self._origin = "none"
            self._capture = False
            self._enabled = False

    def load_dark(self, frame, *, context=None, origin="loaded image; acquisition settings unverified"):
        array = np.array(raw_frame(frame), copy=True, order="C")
        array.setflags(write=False)
        if context is not None and (
            not isinstance(context, CameraContext) or not math.isfinite(context.exposure_s)
            or not math.isfinite(context.gain) or context.exposure_s <= 0 or context.gain <= 0
            or not isinstance(context.device, str) or not context.device
        ):
            raise ValueError("Invalid dark acquisition metadata")
        with self._lock:
            self._dark, self._context, self._origin = array, context, origin
            self._capture = False

    def dark_snapshot(self):
        with self._lock:
            if self._dark is None:
                raise ValueError("No dark image captured or loaded")
            return self._dark.copy(), self._context, self._origin

    def process(self, frame, context, *, acquired_at=None):
        raw = raw_frame(frame)
        with self._lock:
            if self._capture:
                self._dark = np.array(raw, copy=True, order="C")
                self._dark.setflags(write=False)
                self._context, self._origin = context, "captured raw frame"
                self._capture = False
            dark, bound, origin = self._dark, self._context, self._origin
            enabled, size, white = self._enabled, self._size, self._white
            self._sequence += 1
            sequence = self._sequence
            if dark is not None and dark.shape == raw.shape and dark.dtype == raw.dtype and bound is None:
                # Bind an unverified image once, never silently rebind after settings
                # changes. This does not certify its exposure/gain or illumination.
                self._context = bound = context
        status, compatible = "No dark image", False
        if dark is not None:
            if dark.shape != raw.shape or dark.dtype != raw.dtype:
                status = "Dark incompatible: raw shape/dtype mismatch; subtraction bypassed"
            elif bound != context:
                status = "Dark incompatible: exposure/gain/device changed; recapture or reload"
            else:
                compatible = True
                status = origin + (" | SUBTRACTING" if enabled else " | subtraction off")
        # Decimate before arithmetic: pointwise subtraction commutes with this
        # nearest-neighbour preview. Dark storage/capture stays full-resolution.
        stride = max(1, math.ceil(raw.shape[1] / size[0]), math.ceil(raw.shape[0] / size[1]))
        view = raw[::stride, ::stride]
        corrected = enabled and compatible
        if corrected:
            # Signed subtraction prevents unsigned wrap; negatives display as zero.
            values = np.maximum(view.astype(np.int32) - dark[::stride, ::stride].astype(np.int32), 0)
        else:
            values = view
        if raw.dtype == np.uint16:
            pixels = np.asarray(np.minimum(values.astype(np.int32) * 255 // white, 255), dtype=np.uint8)
        else:
            pixels = np.asarray(values, dtype=np.uint8)
        pixels = np.array(pixels, copy=True, order="C")
        pixels.setflags(write=False)
        return PreviewFrame(pixels, sequence, time.monotonic() if acquired_at is None else acquired_at,
                            raw.shape, str(raw.dtype), status, corrected)
