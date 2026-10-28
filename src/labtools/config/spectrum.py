"""Validated, Qt/native-free requests for the opt-in spectrum service."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SpectrumSettings:
    """Requested settings, not verified hardware readbacks or a calibration.

    configuration_id identifies the maintainer-reviewed preset/ROI/grating/
    calibration context. Change it after changes not represented by fields.
    No automatic temperature stability or physical shutter check is implied.
    """

    configuration_id: str
    preset: str
    exposure_s: float
    gain: int
    speed: int
    slit_width_mm: float
    start_nm: float
    end_nm: float
    overlap_pixels: int = 20
    n_frames: int = 1
    combine_mode: str = "single"
    backend: str = "real"

    def validate(self) -> None:
        if (
            not isinstance(self.configuration_id, str)
            or not self.configuration_id.strip()
        ):
            raise ValueError("A reviewed configuration_id is required")
        if self.preset not in {"syncerity", "symphony"}:
            raise ValueError("Unknown detector preset")
        if self.backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        for name in ("exposure_s", "slit_width_mm", "start_nm", "end_nm"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.exposure_s <= 0 or self.slit_width_mm <= 0:
            raise ValueError("Exposure and slit width must be positive")
        if self.start_nm < 0 or self.end_nm <= self.start_nm:
            raise ValueError("Require 0 <= start_nm < end_nm")
        for name in ("gain", "speed", "overlap_pixels", "n_frames"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        if min(self.gain, self.speed, self.overlap_pixels) < 0 or self.n_frames < 1:
            raise ValueError("Invalid token, overlap or frame count")
        if self.combine_mode not in {"single", "mean", "median", "sigma_clip"}:
            raise ValueError("Unknown frame combination mode")
        if self.combine_mode == "single" and self.n_frames != 1:
            raise ValueError("single requires one frame")
        if self.combine_mode in {"median", "sigma_clip"} and self.n_frames < 3:
            raise ValueError("median and sigma_clip require at least three frames")
