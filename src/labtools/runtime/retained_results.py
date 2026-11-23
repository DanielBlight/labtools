"""Export retained run data without device calls or reacquisition.

Arrays are NPZ members; JSON describes the original settings, types and run order.
Only the current run is retained by a panel. A new run replaces that retention.
"""

import json
import math
import uuid
from contextlib import suppress
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np


def export_retained(root, result, *, label="experiment", settings=None):
    """Write a new unique archive folder; never overwrite an earlier export."""
    root = Path(root)
    target = root / (label + "-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    arrays = {}
    def encode(value, key="run"):
        if isinstance(value, np.ndarray):
            name = f"array_{len(arrays):06d}"
            arrays[name] = value
            return {"array": name, "dtype": str(value.dtype), "shape": list(value.shape)}
        if isinstance(value, np.generic):
            return encode(value.item(), key)
        if is_dataclass(value):
            return {"type": type(value).__name__, "fields": {f.name: encode(getattr(value, f.name), key + "." + f.name) for f in fields(value)}}
        if isinstance(value, dict):
            return {str(k): encode(v, key + "." + str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [encode(v, key + f"[{i}]") for i, v in enumerate(value)]
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, float) and not math.isfinite(value):
            return {"nonfinite": str(value)}
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise TypeError("Unsupported retained result value: " + type(value).__name__)
    document = {"schema_version": 1, "label": label, "settings": encode(settings), "result": encode(result)}
    target.mkdir(parents=True, exist_ok=False)
    try:
        np.savez_compressed(target / "arrays.npz", **arrays)
        (target / "run.json").write_text(json.dumps(document, indent=2, allow_nan=False), encoding="utf-8")
        (target / "README.txt").write_text("Retained acquisition export. run.json references arrays.npz members. Load NPZ with allow_pickle=False. No reacquisition was performed.\n")
    except BaseException:
        # A failed export is not reported as complete; retained data remains in RAM.
        with suppress(OSError):
            (target / "EXPORT_FAILED.txt").write_text("Export did not complete; retry from the retained run.\n")
        raise
    return target
