"""Source-backed map/spectrum inputs, independent of anneal approval fields.

Schema 2 describes migrated software settings, never connected-device acceptance.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

from labtools.config.native_candidate import (
    CandidatePreflight,
    NativeCandidatePlan,
    SourceStamp,
    _json,
    _label,
)
from labtools.config.workspace import WorkspaceConfig
from labtools.measurements.recipes import load_recipe

RUNTIME_INPUTS = (
    "LabJack U6 selection remains u6.U6(); physical serial is not recorded in the source.",
    "Monochromator selection remains first discovered; physical identity is not recorded.",
    "Saved lab-PC QSettings values were not captured; migrated recipes are startup defaults.",
    "Installed ICL settings, grating calibration, SDK/driver versions and device readbacks were not captured.",
    "Source voltage envelopes are software limits, not measured or certified hardware ratings.",
    "Physical shared-shutter state and connected-device acceptance remain unverified.",
)
PROFILE_FIELDS = {
    "schema_version", "profile_id", "origin", "mirror_dio_pin", "spad_gate_pin",
    "gate_active_high", "minimum_mirror_voltage_v", "maximum_mirror_voltage_v",
    "home_x_voltage_v", "home_y_voltage_v", "counter_address", "counter_port",
    "labjack_selection", "monochromator_selection", "detectors",
}
DETECTOR_FIELDS = {
    "ccd_index", "expected_device_type", "expected_chip_width", "expected_chip_height",
    "expected_serial_number", "grating", "mirror_position", "roi", "default_gain",
    "default_speed", "gains", "speeds", "minimum_exposure_s",
}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_profile(data):
    if not isinstance(data, dict) or set(data) != PROFILE_FIELDS:
        raise ValueError("Source profile fields must match schema 2 exactly")
    if type(data["schema_version"]) is not int or data["schema_version"] != 2:
        raise ValueError("Source profile schema_version must be 2")
    if not _label(data["profile_id"]) or data["origin"] != "working-lab-source":
        raise ValueError("Source profile needs an identity and working-lab-source origin")
    for field, upper in (("mirror_dio_pin", 14), ("spad_gate_pin", 15)):
        if type(data[field]) is not int or not 0 <= data[field] <= upper:
            raise ValueError(f"Invalid {field}")
    if data["spad_gate_pin"] in {data["mirror_dio_pin"], data["mirror_dio_pin"] + 1}:
        raise ValueError("Gate overlaps mirror I2C pins")
    if data["gate_active_high"] is not True:
        raise ValueError("Existing gate provider requires active-high wiring")
    low, high = data["minimum_mirror_voltage_v"], data["maximum_mirror_voltage_v"]
    if not _finite(low) or not _finite(high) or not low < high:
        raise ValueError("Invalid mirror software envelope")
    if (type(data["home_x_voltage_v"]) not in (int, float)
            or type(data["home_y_voltage_v"]) not in (int, float)
            or data["home_x_voltage_v"] != 0 or data["home_y_voltage_v"] != 0
            or not low <= 0 <= high):
        raise ValueError("Existing map provider requires zero home inside the envelope")
    if not _label(data["counter_address"]) or data["counter_port"] != 5555 or type(data["counter_port"]) is not int:
        raise ValueError("Counter requires an address and existing SCPI port 5555")
    if data["labjack_selection"] != "u6.U6()" or data["monochromator_selection"] != "first-discovered":
        raise ValueError("Unsupported device-selection policy; no new native selection implemented")
    detectors = data["detectors"]
    if not isinstance(detectors, dict) or set(detectors) != {"syncerity", "symphony"}:
        raise ValueError("Both existing detector presets are required")
    for preset, detector in detectors.items():
        if not isinstance(detector, dict) or set(detector) != DETECTOR_FIELDS:
            raise ValueError(f"Invalid detector fields: {preset}")
        for field in ("ccd_index", "expected_chip_width", "expected_chip_height", "default_gain", "default_speed"):
            if type(detector[field]) is not int or detector[field] < 0:
                raise ValueError(f"Invalid detector {field}: {preset}")
        if not detector["expected_chip_width"] or not detector["expected_chip_height"]:
            raise ValueError("Detector dimensions must be positive")
        for field in ("expected_device_type", "expected_serial_number"):
            if not _label(detector[field]):
                raise ValueError(f"Missing detector {field}")
        if detector["grating"] not in {"FIRST", "SECOND", "THIRD"} or detector["mirror_position"] not in {"AXIAL", "LATERAL"}:
            raise ValueError("Unsupported optical preset")
        if not _finite(detector["minimum_exposure_s"]) or detector["minimum_exposure_s"] <= 0:
            raise ValueError("Invalid detector exposure floor")
        for field, default in (("gains", "default_gain"), ("speeds", "default_speed")):
            options = detector[field]
            if (not isinstance(options, list) or not options
                    or any(not isinstance(item, list) or len(item) != 2
                           or not _label(item[0]) or type(item[1]) is not int for item in options)
                    or detector[default] not in {item[1] for item in options}):
                raise ValueError(f"Invalid detector {field}")
        roi = detector["roi"]
        if not isinstance(roi, dict) or set(roi) != {"x_size", "x_bin", "y_origin", "y_size", "y_bin"}:
            raise ValueError("Unsupported source ROI")
        if any(type(value) is not int or value < 0 for value in roi.values()):
            raise ValueError("Invalid ROI values")
        if (min(roi["x_size"], roi["y_size"], roi["x_bin"], roi["y_bin"]) <= 0
                or roi["x_size"] > detector["expected_chip_width"]
                or roi["y_origin"] + roi["y_size"] > detector["expected_chip_height"]
                or roi["x_size"] % roi["x_bin"] or roi["y_size"] % roi["y_bin"]):
            raise ValueError("ROI exceeds detector or has invalid binning")
    return data


def preflight_source_candidate(manifest_path, data):
    errors, paths, stamps = [], {}, []
    fields = {"schema_version", "configuration_id", "resources", "source_profile", "map_recipe", "spectrum_recipe", "source_record"}
    try:
        if set(data) != fields or type(data["schema_version"]) is not int or data["schema_version"] != 2:
            raise ValueError("Source candidate fields must match schema 2 exactly")
        if not _label(data["configuration_id"]):
            raise ValueError("configuration_id is required")
        resources = data["resources"]
        if (not isinstance(resources, dict) or set(resources) != {"labjack", "counter", "spectrometer", "optical_path"}
                or not all(_label(value) for value in resources.values()) or len(set(resources.values())) != 4):
            raise ValueError("Four distinct logical resource labels are required, not invented physical serials")
        stamps.append(SourceStamp("manifest", manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest()))
        for field in ("source_profile", "map_recipe", "spectrum_recipe", "source_record"):
            if not _label(data[field]):
                raise ValueError(f"Missing {field}")
            path = Path(data[field]).expanduser()
            path = (manifest_path.parent / path).resolve()
            content = path.read_bytes()
            if not content.strip():
                raise ValueError(f"Empty {field}")
            paths[field] = path
            stamps.append(SourceStamp(field, path, hashlib.sha256(content).hexdigest()))
        profile = validate_profile(_json(paths["source_profile"]))
        record = _json(paths["source_record"])
        if (not isinstance(record, dict) or record.get("origin") != "working-lab-source"
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("snapshot_sha256", "")))
                or not record.get("sources") or not record.get("claims")):
            raise ValueError("Missing working-lab source linkage")
        for field in ("map_recipe", "spectrum_recipe"):
            raw = _json(paths[field])
            if field == "spectrum_recipe" and (
                raw.get("recipe", {}).get("dark_mode") != "none"
                or raw.get("recipe", {}).get("dark_record_path") is not None
            ):
                raise ValueError("Base spectrum recipe must not open a dark archive")
        mapping = load_recipe(paths["map_recipe"])
        spectrum = load_recipe(paths["spectrum_recipe"])
        if mapping.kind != "intensity_map" or mapping.backend != "real" or mapping.request.resume_directory is not None:
            raise ValueError("Native map base recipe required, without resume directory")
        if spectrum.kind != "spectrum" or spectrum.backend != "real":
            raise ValueError("Native spectrum base recipe required")
        mapping = mapping.request.config
        settings = spectrum.request.settings
        if settings.configuration_id != data["configuration_id"]:
            raise ValueError("Spectrum configuration identity mismatch")
        for field in ("mirror_dio_pin", "spad_gate_pin"):
            if getattr(mapping, field) != profile[field]:
                raise ValueError(f"Map/profile {field} mismatch")
        if mapping.time_controller_address != profile["counter_address"]:
            raise ValueError("Map/profile counter address mismatch")
        if not mapping.safe_voltage_min_v <= 0 <= mapping.safe_voltage_max_v:
            raise ValueError("Map software envelope must include the existing zero home")
        if (mapping.safe_voltage_min_v < profile["minimum_mirror_voltage_v"]
                or mapping.safe_voltage_max_v > profile["maximum_mirror_voltage_v"]):
            raise ValueError("Map exceeds source software envelope")
        detector = profile["detectors"][settings.preset]
        if (settings.exposure_s < detector["minimum_exposure_s"]
                or settings.gain not in {item[1] for item in detector["gains"]}
                or settings.speed not in {item[1] for item in detector["speeds"]}):
            raise ValueError("Spectrum settings do not match source detector options")
        reservation = WorkspaceConfig(
            configuration_id=data["configuration_id"], resources=tuple(resources.values()),
            map_resources=tuple(resources[name] for name in ("labjack", "counter", "optical_path")),
            spectrum_resources=tuple(resources[name] for name in ("spectrometer", "optical_path")),
        )
        reservation.validate()
        plan = NativeCandidatePlan(data["configuration_id"], profile["profile_id"], reservation,
                                   mapping, spectrum.request, tuple(stamps), profile)
        return CandidatePreflight((), plan, RUNTIME_INPUTS)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        errors.append({"field": "source_candidate", "message": str(error)})
    return CandidatePreflight(tuple(errors), runtime_inputs=RUNTIME_INPUTS)
