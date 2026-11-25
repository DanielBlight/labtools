"""Validated read-only dataset tree shared by offline viewers."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


class AnalysisError(ValueError):
    """Invalid data or unsupported analysis request, safe to show to an operator."""


class LoadCancelled(AnalysisError):
    """Loading was cancelled without publishing a partial dataset."""


def axis(values, name):
    values = np.asarray(values)
    if values.ndim != 1 or not values.size or not np.isfinite(values).all():
        raise AnalysisError(f"{name} must be a nonempty finite one-dimensional axis")
    delta = np.diff(values)
    if values.size > 1 and not (np.all(delta > 0) or np.all(delta < 0)):
        raise AnalysisError(f"{name} must be strictly monotonic; duplicate coordinates are ambiguous")
    return values


@dataclass
class Dataset:
    """Arrays belong to the source; processing must allocate derived outputs."""

    label: str
    kind: str
    source: Path
    arrays: dict[str, np.ndarray] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list['Dataset'] = field(default_factory=list)
    synthetic: bool = False
    status: str = "unknown"
    key: str = "root"

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def validate(self):
        a = self.arrays
        if self.kind in {"map", "cube"}:
            x, y = axis(a['x'], 'X'), axis(a['y'], 'Y')
            mask = a['mask']
            if mask.shape != (y.size, x.size) or mask.dtype.kind != 'b':
                raise AnalysisError("Completion mask must be boolean and match the Y/X grid")
            if self.kind == 'cube':
                w = axis(a['wavelength'], 'Wavelength')
                for name in ('raw', 'dark'):
                    if name in a and a[name].shape not in {(y.size, x.size, w.size), (w.size,)}:
                        raise AnalysisError(f'Cube {name} has an incompatible shape')
                if 'raw' in a and a['raw'].shape != (y.size, x.size, w.size):
                    raise AnalysisError('Raw cube must match the saved intensity shape')
                if a['intensity'].shape != (y.size, x.size, w.size):
                    raise AnalysisError("Cube shape must be (Y, X, wavelength)")
            else:
                for name, value in a.items():
                    if name in {'x', 'y', 'mask', 'channels'}:
                        continue
                    if value.ndim not in {2, 3} or value.shape[-2:] != mask.shape:
                        raise AnalysisError(f"Map array {name} does not match the Y/X grid")
                if not any(n in a for n in ('rates', 'counts', 'summed')):
                    raise AnalysisError("Map contains no counts or count rates")
        elif self.kind == 'spectrum':
            w = axis(a['wavelength'], 'Wavelength')
            for name, value in a.items():
                if name != 'wavelength' and value.shape != w.shape:
                    raise AnalysisError(f"Spectrum array {name} does not match wavelength")
            if 'intensity' not in a:
                raise AnalysisError("Spectrum has no intensity")
        elif self.kind == 'anneal':
            if not a or not a.get('elapsed_s', np.array([])).size:
                raise AnalysisError('Anneal log contains no saved exposure positions')
            length = a['elapsed_s'].size
            if any(value.ndim != 1 or value.size != length for value in a.values()):
                raise AnalysisError('Anneal log columns must have matching lengths')
            if not np.isfinite(a['elapsed_s']).all() or np.any(np.diff(a['elapsed_s']) < 0):
                raise AnalysisError('Anneal elapsed time must be finite and non-decreasing')
        for value in a.values():
            if value.dtype.kind not in 'biuf':
                raise AnalysisError("Only numeric, pickle-free arrays are supported")
            value.flags.writeable = False
        return self
