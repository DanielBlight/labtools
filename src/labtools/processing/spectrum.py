"""Frame combination shared by signal and dark acquisition."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np

CombineMode = Literal["single", "mean", "median", "sigma_clip"]


def combine_frames(
    frames: Sequence[np.ndarray], mode: CombineMode, k_sigma: float = 3.0
) -> np.ndarray:
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
    if not np.isfinite(k_sigma) or k_sigma <= 0:
        raise ValueError("Clipping threshold must be finite and positive")
    centre = np.median(stacked, axis=0)
    deviations = np.abs(stacked - centre)
    scale = 1.4826 * np.median(deviations, axis=0)
    keep = deviations <= k_sigma * scale
    count = keep.sum(axis=0)
    total = np.sum(stacked, axis=0, where=keep, dtype=float)
    # A degenerate spread or no strict majority is not grounds for averaging
    # an arbitrary subset. Use the robust centre for those channels instead.
    return np.divide(total, count, out=np.array(centre, dtype=float),
                     where=(scale > 0) & (count > len(frames) // 2))
