"""Camera acquisition/preview pump on one caller-owned thread; no Qt or SDK imports."""

import time
from threading import Lock

from labtools.processing.camera_preview import CameraContext


class CameraTargets:
    def __init__(self, exposure_s=.02, gain=1.):
        self._lock = Lock()
        self.update(exposure_s, gain)

    def update(self, exposure_s, gain):
        import math

        if not math.isfinite(exposure_s) or not .00001 <= exposure_s <= 10:
            raise ValueError("Exposure must be 0.01 to 10000 ms")
        if not math.isfinite(gain) or not 1 <= gain <= 100:
            raise ValueError("Gain must be 1 to 100")
        with self._lock:
            self._values = (float(exposure_s), float(gain))

    def snapshot(self):
        with self._lock:
            return self._values


def native_camera_factory(**kwargs):
    # Only explicit Start reaches this import, on the camera worker thread.
    from labtools.devices.uc480_camera import ThorlabsUC480Camera

    return ThorlabsUC480Camera(**kwargs)


def pump_camera(*, targets, processor, mailbox, stop, connected, factory=native_camera_factory):
    """No frame signals, artificial capture delay, handle sharing or unbounded queue."""
    requested = targets.snapshot()
    processor.cancel_capture()
    if stop.is_set():
        return
    with factory(exposure_s=requested[0]) as camera:
        maximum_gain = camera.get_max_gains()[0]
        gain = camera.set_master_gain(min(requested[1], maximum_gain))
        exposure = camera.get_exposure()
        device = str(camera.get_device_info())
        connected({"device_info": device, "maximum_gain": maximum_gain,
                   "applied_gain": gain, "exposure_s": exposure})
        camera.start_live(buffer_frames=3)
        while not stop.is_set():
            new = targets.snapshot()
            if new != requested:
                if new[0] != requested[0]:
                    exposure = camera.set_exposure(new[0])
                if new[1] != requested[1]:
                    gain = camera.set_master_gain(min(new[1], maximum_gain))
                requested = new
                # Retain the existing transient-frame discard after SDK changes.
                for _ in range(3):
                    if stop.is_set():
                        break
                    camera.read_latest(timeout_s=max(1., exposure + .5))
                if stop.is_set():
                    break
            frame = camera.read_latest(timeout_s=max(1., exposure + .5))
            acquired = time.monotonic()
            if stop.is_set():
                break
            mailbox.put(processor.process(frame, CameraContext(exposure, gain, device), acquired_at=acquired))
    processor.cancel_capture()
