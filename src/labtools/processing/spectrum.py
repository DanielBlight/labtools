"""Frame combination shared by signal and dark acquisition.

Preserves historical single-pass mean/population-standard-deviation clipping,
not a median/MAD or iterative estimator. Acquisition validation stays in the wrapper.
"""
from __future__ import annotations
from collections.abc import Sequence
from typing import Literal
import numpy as np

CombineMode = Literal["single", "mean", "median", "sigma_clip"]


def combine_frames(frames: Sequence[np.ndarray], mode: CombineMode,
                   k_sigma: float = 3.0) -> np.ndarray:
    """Reduce acquired frames without changing acquisition ordering."""
    if mode not in ("single", "mean", "median", "sigma_clip"):
        raise ValueError(f"Unsupported frame combination mode {mode!r}.")
    if mode == "single":
        return frames[0]
    stacked = np.stack(frames)
    if mode == "mean":
        return np.mean(stacked, axis=0)
    if mode == "median":
        return np.median(stacked, axis=0)
    mean = stacked.mean(axis=0)
    std = stacked.std(axis=0)
    mask = np.abs(stacked - mean) > k_sigma * std
    clean = np.where(mask, np.nan, stacked)
    return np.nanmean(clean, axis=0)
