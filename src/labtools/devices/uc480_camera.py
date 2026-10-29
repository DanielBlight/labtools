"""pyLabLib wrapper for the first available Thorlabs UC480 camera."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

import numpy as np
from numpy.typing import NDArray


class UC480CameraError(RuntimeError):
    """Raised when a UC480 camera operation fails."""


@dataclass(frozen=True)
class UC480CameraInfo:
    """Basic information reported for an available UC480 camera."""

    camera_id: int
    device_id: int
    model: str
    serial_number: str
    in_use: bool
    status: int


class ThorlabsUC480Camera:
    """Control the first available Thorlabs UC480 camera via pyLabLib."""

    def __init__(
        self,
        *,
        exposure_s: float = 0.02,
        mirror_horizontal: bool = True,
    ) -> None:
        if exposure_s <= 0:
            raise ValueError("exposure_s must be greater than zero")
        self.exposure_s = float(exposure_s)
        self.mirror_horizontal = bool(mirror_horizontal)
        self._camera = None
        self._live = False
        self._acquisition_state = "idle"
        self._teardown_started = False

    @staticmethod
    def _module():
        try:
            from pylablib.devices import uc480
        except ImportError as exc:
            raise UC480CameraError(
                "pyLabLib is unavailable. Install 'pylablib-lightweight'."
            ) from exc
        return uc480

    @classmethod
    def list_cameras(cls) -> list[UC480CameraInfo]:
        """Return cameras reported by the Thorlabs UC480 backend."""
        return [
            UC480CameraInfo(
                camera_id=int(camera.cam_id),
                device_id=int(camera.dev_id),
                model=str(camera.model),
                serial_number=str(camera.serial_number),
                in_use=bool(camera.in_use),
                status=int(camera.status),
            )
            for camera in cls._module().list_cameras(backend="uc480")
        ]

    @property
    def is_connected(self) -> bool:
        return self._camera is not None

    @staticmethod
    def _retain_cleanup(primary: BaseException, cleanup: BaseException) -> None:
        previous = getattr(primary, "_uc480_cleanup_failures", ())
        primary._uc480_cleanup_failures = (*previous, cleanup)
        primary.add_note(f"UC480 cleanup also failed: {cleanup!r}")

    def _ensure_usable(self) -> None:
        if self._teardown_started:
            raise UC480CameraError(
                "UC480 teardown started; reconnect and commands are refused"
            )

    def connect(self) -> None:
        """Open camera zero and apply exposure, cleaning partial startup."""
        self._ensure_usable()
        if self.is_connected:
            return
        try:
            self._camera = self._module().UC480Camera(cam_id=0, backend="uc480")
            self.set_exposure(self.exposure_s)
        except BaseException as primary:
            try:
                self.close()
            except BaseException as cleanup:  # noqa: BLE001 - preserve primary/cancellation
                self._retain_cleanup(primary, cleanup)
            raise

    def close(self) -> None:
        """Attempt stop and close independently, retaining uncertain ownership."""
        import logging

        if getattr(self, "_teardown_started", False) and self._camera is None:
            return
        self._teardown_started = True
        camera = self._camera
        if camera is None:
            self._live = False
            self._acquisition_state = "idle"
            return
        failures = []
        state = getattr(self, "_acquisition_state", "live" if self._live else "idle")
        if state in {"setup", "live"}:
            try:
                camera.stop_acquisition()
            except BaseException as exc:
                logging.getLogger(__name__).exception("UC480 stop failed")
                failures.append(exc)
            else:
                self._acquisition_state = "idle"
                self._live = False
        try:
            camera.close()
        except BaseException as exc:
            logging.getLogger(__name__).exception("UC480 close failed")
            failures.append(exc)
        else:
            self._live = False
            self._acquisition_state = "idle"
        self._camera = None
        self._live = False
        if failures:
            primary = next(
                (error for error in failures if not isinstance(error, Exception)), None
            )
            if primary is not None:
                for failure in failures:
                    if failure is not primary:
                        self._retain_cleanup(primary, failure)
                raise primary
            raise UC480CameraError("Camera cleanup failed") from ExceptionGroup(
                "UC480 shutdown failures", failures
            )

    def _connected_camera(self):
        self._ensure_usable()
        if self._camera is None:
            raise UC480CameraError("UC480 camera is not connected")
        return self._camera

    def set_exposure(self, exposure_s: float) -> float:
        """Set exposure in seconds and return its readback."""
        if exposure_s <= 0:
            raise ValueError("exposure_s must be greater than zero")
        reported = float(self._connected_camera().set_exposure(float(exposure_s)))
        self.exposure_s = reported
        return reported

    def get_exposure(self) -> float:
        return float(self._connected_camera().get_exposure())

    def get_device_info(self) -> object:
        return self._connected_camera().get_device_info()

    def get_gains(self) -> tuple[float, float, float, float]:
        """Return master, red, green, and blue gain factors."""
        values = self._connected_camera().get_gains()
        return tuple(float(value) for value in values)

    def get_max_gains(self) -> tuple[float, float, float, float]:
        """Return device-specific maximum gain factors."""
        values = self._connected_camera().get_max_gains()
        return tuple(float(value) for value in values)

    def set_master_gain(self, gain: float) -> float:
        """Set master gain, clamped to the camera-reported range."""
        maximum = self.get_max_gains()[0]
        requested = min(max(float(gain), 1.0), maximum)
        reported = self._connected_camera().set_gains(master=requested)
        return float(reported[0])

    def start_live(self, *, buffer_frames: int = 20) -> None:
        """Start continuous sequence acquisition."""
        if buffer_frames < 2:
            raise ValueError("buffer_frames must be at least two")
        if self._live:
            return
        camera = self._connected_camera()
        try:
            camera.setup_acquisition(nframes=int(buffer_frames))
            self._acquisition_state = "setup"
            camera.start_acquisition()
        except BaseException as primary:
            if self._acquisition_state == "setup":
                try:
                    camera.stop_acquisition()
                except BaseException as cleanup:  # noqa: BLE001 - preserve primary/cancellation
                    self._retain_cleanup(primary, cleanup)
                else:
                    self._acquisition_state = "idle"
            raise
        self._acquisition_state = "live"
        self._live = True

    def stop_live(self) -> None:
        """Stop continuous acquisition if active."""
        if self._live:
            self._connected_camera().stop_acquisition()
            self._live = False
            self._acquisition_state = "idle"

    def read_latest(self, *, timeout_s: float = 1.0) -> NDArray[np.generic]:
        """Wait for a frame and return the newest buffered image."""
        if not self._live:
            raise UC480CameraError("Continuous acquisition is not running")
        camera = self._connected_camera()
        camera.wait_for_frame(timeout=timeout_s)
        frame = camera.read_newest_image()
        if frame is None:
            raise UC480CameraError("Camera reported a frame but returned no image")
        return self._prepare_frame(np.asarray(frame))

    def snap(self) -> NDArray[np.generic]:
        """Acquire one standalone frame."""
        frame = np.asarray(self._connected_camera().snap())
        return self._prepare_frame(frame)

    def _prepare_frame(self, frame: NDArray[np.generic]) -> NDArray[np.generic]:
        if frame.ndim not in {2, 3}:
            raise UC480CameraError(
                f"Unexpected camera frame shape {frame.shape}; expected 2D or 3D"
            )
        if self.mirror_horizontal:
            frame = np.flip(frame, axis=1)
        return np.array(frame, copy=True, order="C")

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            self.close()
        except BaseException as cleanup:
            if exc_value is None:
                raise
            self._retain_cleanup(exc_value, cleanup)
