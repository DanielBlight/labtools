"""Versioned, pickle-free dark/result archives for the opt-in spectrum service.

Archives are exclusive-create to avoid silently replacing measurements. Legacy
CSV remains available through DarkSpectrum, but carries no settings provenance.
"""

import json
from dataclasses import asdict, fields
from pathlib import Path

import numpy as np

from labtools.acquisition.spectrum_service import DarkRecord, SpectrumResult
from labtools.config.spectrum import SpectrumSettings


def _save(path, metadata, **arrays):
    path = Path(path)
    handle = path.open("xb")  # Failure here must never remove an existing file.
    try:
        with handle:
            np.savez_compressed(handle, metadata=json.dumps(metadata), **arrays)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def save_dark_record(path: str | Path, dark: DarkRecord) -> None:
    _save(
        path,
        {
            "schema_version": 1,
            "kind": "dark",
            "settings": asdict(dark.settings),
            "record_id": dark.record_id,
            "captured_at": dark.captured_at,
            "synthetic_data": dark.settings.backend == "simulation",
        },
        wavelength_nm=dark.wavelength_nm,
        intensity=dark.intensity,
    )


def load_dark_record(path: str | Path) -> DarkRecord:
    with np.load(path, allow_pickle=False) as data:
        if set(data.files) != {"metadata", "wavelength_nm", "intensity"}:
            raise ValueError("Unexpected dark archive members")
        meta = json.loads(str(data["metadata"].item()))
        expected = {
            "schema_version",
            "kind",
            "settings",
            "record_id",
            "captured_at",
            "synthetic_data",
        }
        if not isinstance(meta, dict) or set(meta) != expected:
            raise ValueError("Invalid dark metadata")
        if (
            type(meta["schema_version"]) is not int
            or meta["schema_version"] != 1
            or meta["kind"] != "dark"
        ):
            raise ValueError("Unsupported dark archive schema")
        if not isinstance(meta["settings"], dict) or set(meta["settings"]) != {
            field.name for field in fields(SpectrumSettings)
        }:
            raise ValueError("Dark archive must specify every settings field")
        settings = SpectrumSettings(**meta["settings"])
        settings.validate()
        if type(meta["synthetic_data"]) is not bool or meta["synthetic_data"] != (
            settings.backend == "simulation"
        ):
            raise ValueError("Dark provenance disagrees with backend")
        return DarkRecord(
            settings,
            data["wavelength_nm"],
            data["intensity"],
            meta["record_id"],
            meta["captured_at"],
        )


def save_spectrum_result(path: str | Path, result: SpectrumResult) -> None:
    arrays = {"wavelength_nm": result.wavelength_nm, "intensity": result.intensity}
    if result.raw_intensity is not None:
        arrays["raw_intensity"] = result.raw_intensity
    _save(
        path,
        {
            "schema_version": 1,
            "kind": "spectrum",
            "settings": asdict(result.settings),
            "dark_mode": result.dark_mode,
            "dark_record_id": result.dark_record_id,
            "raw_available": result.raw_intensity is not None,
            "synthetic_data": result.settings.backend == "simulation",
        },
        **arrays,
    )
