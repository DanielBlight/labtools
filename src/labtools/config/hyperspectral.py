"""Validated Qt/native-free configuration for hyperspectral acquisition."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass

from labtools.config.spectrum import SpectrumSettings

HYPERSPECTRAL_CONFIG_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class HyperspectralConfig:
    """Reviewed row-major mirror scan with one spectrum at each point."""

    configuration_id: str
    spectrum: SpectrumSettings
    x_start_v: float
    x_stop_v: float
    x_points: int
    y_start_v: float
    y_stop_v: float
    y_points: int
    settle_time_s: float = 0.0
    dark_mode: str = "none"
    backend: str = "simulation"

    def validate(self) -> None:
        if (
            not isinstance(self.configuration_id, str)
            or not self.configuration_id.strip()
        ):
            raise ValueError("A reviewed configuration_id is required")
        self.spectrum.validate()
        if self.backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        if self.spectrum.backend != self.backend:
            raise ValueError("Hyperspectral and spectrum backends must match")
        if self.dark_mode not in {"none", "per_center", "per_frame", "pre_taken"}:
            raise ValueError("Unsupported dark_mode")
        for name in ("x_start_v", "x_stop_v", "y_start_v", "y_stop_v", "settle_time_s"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.settle_time_s < 0:
            raise ValueError("settle_time_s must be non-negative")
        for name in ("x_points", "y_points"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")

    def identity(self) -> str:
        self.validate()
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
