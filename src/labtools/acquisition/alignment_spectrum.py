"""Single-centre repeated spectra. No Qt, laser or range acquisition imports."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
import math
from threading import Event, Lock
import numpy as np


def detector_options(preset):
    from labtools.devices.horiba_spectrometer import HoribaSpectrometer
    return HoribaSpectrometer.preset_options(preset)


def real_spectrometer(*, preset):
    from labtools.devices.horiba_spectrometer import HoribaSpectrometer
    return HoribaSpectrometer(preset=preset)


@dataclass(frozen=True)
class AlignmentConfig:
    preset: str = "syncerity"
    centre_nm: float = 690.0
    exposure_s: float = 0.1
    subtract_dark: bool = False
    gain: int = 2
    speed: int = 0

    def validate(self):
        if self.preset not in {"syncerity", "symphony"}:
            raise ValueError("Select syncerity or symphony")
        for name in ("centre_nm", "exposure_s"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 <= self.centre_nm <= 2200:
            raise ValueError("Centre must be between 0 and 2200 nm (GUI range, not a hardware guarantee)")
        if not 0.02 <= self.exposure_s <= 1000:
            raise ValueError("Exposure must be between 0.02 and 1000 s")
        if type(self.subtract_dark) is not bool:
            raise ValueError("subtract_dark must be a boolean")
        for name in ("gain", "speed"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer token")

    def validate_detector(self, options):
        self.validate()
        for name, field in (("gain", "gains"), ("speed", "speeds")):
            if getattr(self, name) not in {token for label, token in options[field]}:
                raise ValueError(f"Unsupported {name} token for {self.preset}")


@dataclass(frozen=True)
class AlignmentFrame:
    wavelength_nm: np.ndarray
    intensity: np.ndarray
    sequence: int
    actual_centre_nm: float
    acquisition_s: float
    elapsed_s: float


class LatestSpectrum:
    """One-frame mailbox: slow plotting never queues an unbounded history."""
    def __init__(self):
        self._lock = Lock()
        self._frame = None

    def put(self, frame):
        with self._lock:
            self._frame = frame

    def take(self):
        with self._lock:
            frame, self._frame = self._frame, None
            return frame


async def run_alignment(config, stop, on_frame, *, factory=real_spectrometer,
                        options_provider=detector_options, on_status=lambda text: None):
    """One connection and one asyncio loop for a complete Start/Stop session.

    Captures run back-to-back, sequentially, without overlapping requests.
    A fresh closed-shutter dark precedes each signal when selected. Stop does not
    abort an active native operation. No shutter override commands are issued.
    """
    config.validate()
    config.validate_detector(options_provider(config.preset))
    if stop.is_set():
        return 0
    spec = factory(preset=config.preset)
    primary = None
    sequence = 0
    loop = asyncio.get_running_loop()
    session_started = loop.time()
    try:
        on_status("Connecting to HORIBA...")
        await spec.connect()
        if stop.is_set(): return 0
        on_status("Applying detector preset (may move grating and exit mirror)...")
        await spec.configure(gain=config.gain, speed=config.speed,
                             exposure_time=config.exposure_s, roi=None,
                             minimum_exposure_override_s=0.02)
        if stop.is_set(): return 0
        on_status("Moving to the selected centre wavelength...")
        actual = float(await spec.set_wavelength(config.centre_nm))
        if not math.isfinite(actual):
            raise RuntimeError("Non-finite centre wavelength readback")
        if stop.is_set(): return 0
        on_status(f"Acquiring at reported centre {actual:.3f} nm")
        while not stop.is_set():
            started = loop.time()
            dark_x = dark_y = None
            if config.subtract_dark:
                dark_x, dark_y = await spec.get_dark_spectrum(n_frames=1, mode="single")
                dark_x = np.array(dark_x, dtype=float, copy=True)
                dark_y = np.array(dark_y, dtype=float, copy=True)
                if stop.is_set(): break
            x, y = await spec.get_spectrum(n_frames=1, mode="single", dark_frame_mode="none")
            x, y = np.array(x, dtype=float, copy=True), np.array(y, dtype=float, copy=True)
            if x.ndim != 1 or y.ndim != 1 or x.shape != y.shape or not x.size:
                raise RuntimeError("Spectrum must contain matching, nonempty 1D arrays")
            if not np.isfinite(x).all() or not np.isfinite(y).all():
                raise RuntimeError("Spectrum contains non-finite values")
            if config.subtract_dark:
                if (dark_x.ndim != 1 or dark_y.ndim != 1 or dark_x.shape != x.shape
                        or dark_y.shape != y.shape or not np.isfinite(dark_x).all()
                        or not np.isfinite(dark_y).all()
                        or not np.allclose(dark_x, x, rtol=0.0, atol=1e-8)):
                    raise RuntimeError("Dark spectrum arrays or wavelength axis do not match signal")
                y = y - dark_y
                if not np.isfinite(y).all():
                    raise RuntimeError("Dark subtraction produced non-finite values")
            order = np.argsort(x)
            x, y = x[order], y[order]
            x.setflags(write=False)
            y.setflags(write=False)
            sequence += 1
            on_frame(AlignmentFrame(x, y, sequence, actual, loop.time() - started,
                                    loop.time() - session_started))
            await asyncio.sleep(0)  # Yield only; no intentional inter-frame delay.
        return sequence
    except BaseException as exc:
        primary = exc
        raise
    finally:
        # Even a status callback failure must not prevent the disconnect attempt.
        try:
            await spec.disconnect()
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.add_note(f"HORIBA disconnect also failed: {cleanup!r}")
