"""Portable workflow settings, bound to source identity; never hardware profiles."""

import json
from dataclasses import asdict, replace
from pathlib import Path

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.runtime.unified_inputs import _overlay, validate_display

ALIGNMENT_FIELDS = ("preset", "centre_nm", "exposure_s", "subtract_dark", "gain", "speed")


def alignment_defaults(workspace):
    spectrum = workspace.drafts.values["spectrum"]
    backend = "simulation" if getattr(workspace, "simulation_only", False) else "real"
    return AlignmentSettings(workspace.plan.configuration_id, preset=spectrum.preset,
                             centre_nm=(spectrum.start_nm + spectrum.end_nm) / 2,
                             exposure_s=spectrum.exposure_s, gain=spectrum.gain, speed=spectrum.speed, backend=backend)


def validate_alignment(workspace, data):
    if not isinstance(data, dict) or set(data) - set(ALIGNMENT_FIELDS):
        raise ValueError("Unknown alignment setting")
    value = replace(alignment_defaults(workspace), **data)
    value.validate_detector(workspace.plan.hardware_settings["detectors"][value.preset])
    return value


def pack(workspace, drafts, display, alignment=None):
    workspace._require_open()
    workflows = {}
    for name in workspace.drafts.values:
        value = workspace.drafts.validate(name, drafts[name])
        data = asdict(value)
        workflows[name] = {key: str(data[key]) if isinstance(data[key], Path) else list(data[key]) if isinstance(data[key], tuple) else data[key]
                           for key in workspace.drafts.fields[name]}
    workflows["display"] = validate_display(display)
    if alignment is not None:
        workflows["alignment"] = {key: getattr(alignment, key) for key in ALIGNMENT_FIELDS}
        validate_alignment(workspace, workflows["alignment"])
    return {"schema_version": 1, "kind": "labtools-workflow-settings", "configuration_id": workspace.plan.configuration_id,
            "source_fingerprint": workspace.drafts.store.fingerprint,
            "backend": "simulation" if getattr(workspace, "simulation_only", False) else "real", "workflows": workflows}


def unpack(workspace, data):
    workspace._require_open()
    expected = {"schema_version", "kind", "configuration_id", "source_fingerprint", "backend", "workflows"}
    if not isinstance(data, dict) or set(data) != expected or type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["kind"] != "labtools-workflow-settings":
        raise ValueError("Not a supported workflow settings file")
    backend = "simulation" if getattr(workspace, "simulation_only", False) else "real"
    if (data["configuration_id"] != workspace.plan.configuration_id or data["source_fingerprint"] != workspace.drafts.store.fingerprint
            or data["backend"] != backend):
        raise ValueError("Settings belong to a different configuration/source/backend; load the matching configuration first")
    values = data["workflows"]
    required = {"map", "spectrum", "anneal", "display"}
    if not isinstance(values, dict) or not required <= set(values) <= required | {"alignment"}:
        raise ValueError("Settings workflows are incomplete or unknown")
    result = {}
    for name, previous in workspace.drafts.values.items():
        result[name] = workspace.drafts.validate(name, _overlay(previous, values[name], workspace.drafts.fields[name]))
    result["display"] = validate_display(values["display"])
    if "alignment" in values:
        result["alignment"] = validate_alignment(workspace, values["alignment"])
    return result


def read_settings(path):
    path = Path(path)
    if path.stat().st_size > 256_000:
        raise ValueError("Settings file is too large")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate settings key: " + key)
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)
