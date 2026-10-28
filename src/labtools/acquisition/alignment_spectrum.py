"""Validated single-centre alignment requests and immutable frame results."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from labtools.acquisition.spectrum_service import owned_vector


@dataclass(frozen=True)
class AlignmentSettings:
    configuration_id: str
    preset: str = "syncerity"
    centre_nm: float = 690.0
    exposure_s: float = 0.1
    subtract_dark: bool = False
    gain: int = 2
    speed: int = 0
    backend: str = "real"

    def validate(self) -> None:
        if (
            not isinstance(self.configuration_id, str)
            or not self.configuration_id.strip()
        ):
            raise ValueError("A reviewed configuration_id is required")
        if self.preset not in {"syncerity", "symphony"}:
            raise ValueError("Select syncerity or symphony")
        if self.backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        for name in ("centre_nm", "exposure_s"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 <= self.centre_nm <= 2200:
            raise ValueError("Centre must be between 0 and 2200 nm")
        if not 0 < self.exposure_s <= 1000:
            raise ValueError("Exposure must be positive and no greater than 1000 s")
        if type(self.subtract_dark) is not bool:
            raise ValueError("subtract_dark must be a boolean")
        if type(self.gain) is not int or type(self.speed) is not int:
            raise ValueError("Gain and speed must be integer tokens")

    def validate_detector(self, options) -> None:
        self.validate()
        minimum = float(options["minimum_exposure_s"])
        if self.exposure_s < minimum:
            raise ValueError(
                f"Exposure for {self.preset} must be at least {minimum:g} s"
            )
        for name, field in (("gain", "gains"), ("speed", "speeds")):
            if getattr(self, name) not in {token for _, token in options[field]}:
                raise ValueError(f"Unsupported {name} token for {self.preset}")


@dataclass(frozen=True)
class AlignmentResult:
    settings: AlignmentSettings
    wavelength_nm: np.ndarray
    intensity: np.ndarray
    raw_intensity: np.ndarray
    actual_centre_nm: float
    dark_subtracted: bool

    def __post_init__(self) -> None:
        self.settings.validate()
        x = owned_vector(self.wavelength_nm)
        y = owned_vector(self.intensity)
        raw = owned_vector(self.raw_intensity)
        if x.shape != y.shape or x.shape != raw.shape:
            raise ValueError("Alignment result shapes differ")
        if not math.isfinite(self.actual_centre_nm):
            raise ValueError("Alignment centre readback must be finite")
        object.__setattr__(self, "wavelength_nm", x)
        object.__setattr__(self, "intensity", y)
        object.__setattr__(self, "raw_intensity", raw)
