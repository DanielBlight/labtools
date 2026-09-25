"""Read-only connectivity and frame test for a UC480-compatible camera."""

from __future__ import annotations

import argparse

import numpy as np

from labtools.devices.uc480_camera import ThorlabsUC480Camera


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("uc480", "ueye"), default="uc480")
    parser.add_argument("--camera-id", type=int, default=0)
    parser.add_argument("--device-id", type=int)
    parser.add_argument("--exposure-ms", type=float, default=20.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Available cameras:")
    for camera in ThorlabsUC480Camera.list_cameras(backend=args.backend):
        print(camera)

    with ThorlabsUC480Camera(
        camera_id=args.camera_id,
        device_id=args.device_id,
        backend=args.backend,
        exposure_s=args.exposure_ms / 1000.0,
    ) as camera:
        frame = camera.snap()
        print(f"Device: {camera.get_device_info()}")
        print(f"Exposure: {camera.get_exposure() * 1000.0:.3f} ms")
        print(f"Frame shape: {frame.shape}")
        print(f"Frame dtype: {frame.dtype}")
        print(f"Minimum: {np.min(frame)}")
        print(f"Maximum: {np.max(frame)}")
        print(f"Mean: {np.mean(frame):.3f}")


if __name__ == "__main__":
    main()
