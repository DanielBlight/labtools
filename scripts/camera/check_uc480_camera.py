"""Explicit UC480 single-frame diagnostic. Close ThorCam before running."""
import argparse

import numpy as np

from labtools.devices.uc480_camera import ThorlabsUC480Camera


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exposure-ms", type=float, default=20.0)
    args = parser.parse_args()
    if not np.isfinite(args.exposure_ms) or args.exposure_ms <= 0:
        parser.error("Exposure must be finite and positive")
    print(ThorlabsUC480Camera.list_cameras())
    with ThorlabsUC480Camera(exposure_s=args.exposure_ms / 1000) as camera:
        frame = camera.snap()
        print(camera.get_device_info())
        print("Exposure (ms):", camera.get_exposure() * 1000)
        print("Frame:", frame.shape, frame.dtype)
        print("Min / max / mean:", frame.min(), frame.max(), frame.mean())


if __name__ == "__main__":
    main()
