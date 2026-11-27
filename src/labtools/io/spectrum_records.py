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
from labtools.processing.dark_spectrum import DarkSegment


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
    segments = {}
    for index, segment in enumerate(dark.segments):
        segments[f"segment_{index}_wavelength_nm"] = segment.wavelength_nm
        segments[f"segment_{index}_intensity"] = segment.intensity
    _save(
        path,
        {
            "schema_version": 2 if dark.segments else 1,
            **({"centres_nm": [segment.centre_nm for segment in dark.segments]} if dark.segments else {}),
            "kind": "dark",
            "settings": asdict(dark.settings),
            "record_id": dark.record_id,
            "captured_at": dark.captured_at,
            "synthetic_data": dark.settings.backend == "simulation",
        },
        wavelength_nm=dark.wavelength_nm,
        intensity=dark.intensity,
        **segments,
    )


def load_dark_record(path: str | Path) -> DarkRecord:
    with np.load(path, allow_pickle=False) as data:
        if "metadata" not in data.files:
            raise ValueError("Missing dark archive metadata")
        meta = json.loads(str(data["metadata"].item()))
        expected = {
            "schema_version",
            "kind",
            "settings",
            "record_id",
            "captured_at",
            "synthetic_data",
        }
        version = meta.get("schema_version") if isinstance(meta, dict) else None
        if type(version) is not int or version not in {1, 2}:
            raise ValueError("Unsupported dark archive schema")
        members = {"metadata", "wavelength_nm", "intensity"}
        centres = []
        if version == 2:
            expected.add("centres_nm")
            centres = meta.get("centres_nm")
            if not isinstance(centres, list) or not centres or len(centres) > len(data.files):
                raise ValueError("Invalid dark segment centres")
            for index in range(len(centres)):
                members.update((f"segment_{index}_wavelength_nm", f"segment_{index}_intensity"))
        if set(data.files) != members or len(data.files) != len(members):
            raise ValueError("Unexpected dark archive members")
        if set(meta) != expected:
            raise ValueError("Invalid dark metadata")
        if meta["kind"] != "dark":
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
            tuple(DarkSegment(centre, data[f"segment_{index}_wavelength_nm"],
                              data[f"segment_{index}_intensity"])
                  for index, centre in enumerate(centres)),
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
