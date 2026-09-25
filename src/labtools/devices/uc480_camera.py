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

    def connect(self) -> None:
        """Open the first available UC480 camera and apply the exposure."""
        if self.is_connected:
            return
        try:
            self._camera = self._module().UC480Camera(cam_id=0, backend="uc480")
            self.set_exposure(self.exposure_s)
        except Exception as exc:
            self.close()
            raise UC480CameraError(f"Could not open UC480 camera: {exc}") from exc

    def close(self) -> None:
        camera = self._camera
        self._camera = None
        if camera is not None:
            try:
                camera.close()
            except Exception as exc:  # noqa: BLE001
                raise UC480CameraError(f"Could not close UC480 camera: {exc}") from exc

    def _connected_camera(self):
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

    def snap(self) -> NDArray[np.generic]:
        """Acquire one frame and optionally mirror it horizontally."""
        frame = np.asarray(self._connected_camera().snap())
        if frame.ndim not in {2, 3}:
            raise UC480CameraError(
                f"Unexpected camera frame shape {frame.shape}; expected 2D or 3D"
            )
        if self.mirror_horizontal:
            frame = np.flip(frame, axis=1)
        return np.ascontiguousarray(frame)

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
