"""Three-workflow defaults, local anneal limits and whitelisted preferences."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, replace
from pathlib import Path
from typing import get_type_hints

from labtools.config.anneal_types import LaserAnnealConfig
from labtools.config.anneal_workspace import (
    AnnealRecipe,
    load_profile,
    profile_path,
    validate_recipe,
)
from labtools.config.native_candidate import SourceStamp
from labtools.runtime.workspace_preferences import WorkspacePreferences

MAP_FIELDS = (
    "x_start_v", "x_stop_v", "x_points", "y_start_v", "y_stop_v", "y_points",
    "integration_time_s", "settle_time_s", "channels", "channel_thresholds_v", "channel_edges",
    "serpentine", "output_root", "save_results",
)
SPECTRUM_FIELDS = (
    "preset", "exposure_s", "gain", "speed", "slit_width_mm", "start_nm", "end_nm",
    "overlap_pixels", "n_frames", "combine_mode",
)
ANNEAL_FIELDS = (
    "x_start_v", "x_stop_v", "x_points", "y_start_v", "y_stop_v", "y_points", "passes",
    "point_dwell_s", "mirror_settle_s", "serpentine", "anneal_rotation_coordinate",
    "return_rotation_coordinate", "return_rotation_stage", "maximum_open_time_s", "output_root", "save_run_log",
)


def anneal_defaults(plan, explicit_profile=None):
    source = plan.hardware_settings
    config = replace(LaserAnnealConfig(), mirror_dio_pin=source["mirror_dio_pin"],
                     minimum_mirror_voltage_v=source["minimum_mirror_voltage_v"],
                     maximum_mirror_voltage_v=source["maximum_mirror_voltage_v"])
    path = Path(explicit_profile).expanduser().resolve() if explicit_profile is not None else profile_path()
    source_defaults = config
    local = None
    stamp = None
    error = None
    if explicit_profile is not None or path.is_file():
        try:
            raw = path.read_bytes()
            local = load_profile(path)
            stamp = SourceStamp("local_anneal_profile", path, hashlib.sha256(raw).hexdigest())
            config = replace(config, instrument_profile_id=local.profile_id,
                             instrument_profile_sha256=stamp.sha256,
                             minimum_mirror_voltage_v=max(config.minimum_mirror_voltage_v, local.minimum_mirror_voltage_v),
                             maximum_mirror_voltage_v=min(config.maximum_mirror_voltage_v, local.maximum_mirror_voltage_v),
                             mirror_dio_pin=local.mirror_dio_pin, home_x_voltage_v=local.home_x_voltage_v,
                             home_y_voltage_v=local.home_y_voltage_v, sc10_port=local.sc10_port,
                             sc10_baud_rate=local.sc10_baud_rate, sc10_timeout_s=local.sc10_timeout_s,
                             rotation_stage_timeout_s=local.rotation_stage_timeout_s,
                             maximum_open_time_s=min(config.maximum_open_time_s, local.maximum_open_time_s))
            if (config.minimum_mirror_voltage_v >= config.maximum_mirror_voltage_v
                    or not config.minimum_mirror_voltage_v <= config.home_x_voltage_v <= config.maximum_mirror_voltage_v
                    or not config.minimum_mirror_voltage_v <= config.home_y_voltage_v <= config.maximum_mirror_voltage_v):
                raise ValueError("Local anneal envelope/home is incompatible with shared source limits")
            if local.mirror_dio_pin != source["mirror_dio_pin"]:
                raise ValueError("Local anneal mirror wiring differs from shared map wiring")
        except (OSError, ValueError, TypeError) as exc:
            error = str(exc)
            config = source_defaults
    return config, local, stamp, error


def validate_anneal(config, baseline, local=None, profile_error=None):
    if profile_error:
        raise ValueError("Anneal profile unavailable/invalid: " + profile_error)
    if not isinstance(config, LaserAnnealConfig):
        raise TypeError("Anneal draft must be LaserAnnealConfig")
    for name in ("minimum_mirror_voltage_v", "maximum_mirror_voltage_v", "mirror_dio_pin",
                 "home_x_voltage_v", "home_y_voltage_v", "sc10_port", "sc10_baud_rate",
                 "sc10_timeout_s", "rotation_stage_timeout_s", "instrument_profile_id", "instrument_profile_sha256"):
        if getattr(config, name) != getattr(baseline, name):
            raise ValueError("Anneal source-bound field changed: " + name)
    for name, value in asdict(config).items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Anneal value must be finite: " + name)
    for name in ("x_points", "y_points", "passes"):
        if type(getattr(config, name)) is not int:
            raise ValueError("Anneal point counts/passes must be integers")
    if type(config.return_rotation_stage) is not bool or type(config.serpentine) is not bool:
        raise ValueError("Anneal flags must be boolean")
    if config.maximum_open_time_s <= 0 or config.maximum_open_time_s > baseline.maximum_open_time_s:
        raise ValueError("Anneal maximum open time exceeds source/local limit")
    config.validate()
    if local is not None:
        recipe = AnnealRecipe(**{name: str(getattr(config, name)) if name == "output_root" else getattr(config, name)
                                 for name in AnnealRecipe.__dataclass_fields__})
        validate_recipe(recipe, local)
    return config


def _overlay(baseline, values, fields):
    if not isinstance(values, dict) or set(values) - set(fields):
        raise ValueError("Unknown or invalid preference fields")
    converted = {}
    hints = get_type_hints(type(baseline))
    for name, value in values.items():
        original = getattr(baseline, name)
        if isinstance(original, Path):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Invalid output directory")
            value = Path(value)
        elif isinstance(original, tuple):
            if not isinstance(value, list) or not value:
                raise ValueError("Invalid sequence preference")
            exemplar = original[0]
            if any((type(item) is not type(exemplar)) if type(exemplar) is not float
                   else (type(item) not in (int, float) or not math.isfinite(item)) for item in value):
                raise ValueError("Invalid sequence element type")
            value = tuple(value)
        elif hints.get(name) is float:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Invalid numeric preference")
        elif type(value) is not type(original):
            raise ValueError("Invalid preference type: " + name)
        converted[name] = value
    return replace(baseline, **converted)


class UnifiedDrafts:
    def __init__(self, workspace, preferences_path=None, anneal_profile=None):
        self.workspace = workspace
        self.anneal_base, self.local_profile, stamp, self.profile_error = anneal_defaults(workspace.plan, anneal_profile)
        if stamp is not None:
            workspace.plan = replace(workspace.plan, sources=workspace.plan.sources + (stamp,))
        fingerprint = hashlib.sha256(json.dumps([(s.field, s.sha256) for s in workspace.plan.sources]).encode()).hexdigest()
        self.store = WorkspacePreferences(workspace.plan.configuration_id, fingerprint, preferences_path)
        self.values = {"map": workspace.plan.map_config, "spectrum": workspace.plan.spectrum_request.settings,
                       "anneal": self.anneal_base}
        self.fields = {"map": MAP_FIELDS, "spectrum": SPECTRUM_FIELDS, "anneal": ANNEAL_FIELDS}
        self.display = {}
        self.alignment = {}
        for name, saved in self.store.read().items():
            if name == "alignment":
                if isinstance(saved, dict):
                    self.alignment = saved
                continue
            if name == "display":
                try:
                    self.display = validate_display(saved)
                except (ValueError, TypeError) as error:
                    self.store.messages.append("Display preferences ignored: " + str(error))
                continue
            if name not in self.values:
                self.store.messages.append("Ignored unknown preference workflow: " + str(name))
                continue
            try:
                self.values[name] = self.validate(name, _overlay(self.values[name], saved, self.fields[name]))
            except (ValueError, TypeError, OSError) as error:
                self.store.messages.append(f"{name}: {error}; using source defaults")

    def validate(self, name, config):
        if name == "map":
            return self.workspace.workflows.map_config(config)
        if name == "spectrum":
            return self.workspace.workflows.spectrum_settings(config)
        if name == "anneal":
            self.workspace.plan.verify_sources()
            return validate_anneal(config, self.anneal_base, self.local_profile, self.profile_error)
        raise ValueError("Unknown workflow")

    def save(self, **drafts):
        payload = {}
        from labtools.runtime.workspace_settings import (
            ALIGNMENT_FIELDS,
            validate_alignment,
        )

        alignment = drafts.pop("alignment", self.alignment)
        if alignment:
            try:
                value = validate_alignment(self.workspace, alignment)
                self.alignment = {key: getattr(value, key) for key in ALIGNMENT_FIELDS}
                payload["alignment"] = self.alignment
            except (ValueError, TypeError, KeyError) as error:
                self.store.messages.append("Alignment preferences ignored: " + str(error))
        display = drafts.pop("display", self.display)
        self.display = validate_display(display)
        payload["display"] = self.display
        # Preserve last valid workflow independently when another panel is invalid.
        for name, previous in self.values.items():
            try:
                current = self.validate(name, drafts.get(name, previous))
            except (ValueError, TypeError, OSError) as error:
                self.store.messages.append(f"{name} not saved: {error}")
                current = previous
            self.values[name] = current
            data = asdict(current)
            payload[name] = {field: str(data[field]) if isinstance(data[field], Path) else data[field]
                             for field in self.fields[name]}
        self.store.write(payload)


DISPLAY_TYPES = {"focus_enabled": bool, "focus_levels": str, "focus_sweeps": int,
                 "focus_steps": int, "focus_direction": int, "focus_settle": float, "map_log": bool, "map_manual_limits": bool, "map_min": float, "map_max": float,
                 "spectrum_output": str, "spectrum_csv": bool, "spectrum_png": bool,
                 "camera_exposure_ms": float, "camera_gain": float, "camera_interval_ms": float,
                 "camera_white_level": float,
                 "program_mode": str, "program_first_s": float, "program_last_s": float, "program_spacing": str,
                 "cube_dark": str, "cube_output": str, "sequence_measurement": str,
                 "sequence_cycles": int, "sequence_anneals": int, "sequence_measurements": int, "sequence_output": str, "sequence_save_output": bool,
                 "cube_x_start": float, "cube_x_stop": float, "cube_y_start": float, "cube_y_stop": float,
                 "cube_x_points": int, "cube_y_points": int, "cube_settle": float, "cube_save_output": bool, "sequence_spectrum_x": float, "sequence_spectrum_y": float,
                 "sequence_spectrum_settle": float}


def validate_display(data):
    if not isinstance(data, dict) or set(data) - set(DISPLAY_TYPES):
        raise ValueError("Unknown display preference")
    for key, value in data.items():
        kind = DISPLAY_TYPES[key]
        if kind is float:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Display number must be finite")
        elif type(value) is not kind:
            raise ValueError("Invalid display preference type")
    if data.get("map_manual_limits") and data.get("map_min", 0) >= data.get("map_max", 1):
        raise ValueError("Manual colour limits must increase")
    for name, low, high in (("camera_exposure_ms", .01, 10000), ("camera_gain", 1, 100), ("camera_interval_ms", 16, 10000), ("camera_white_level", 1, 65535)):
        if name in data and not low <= data[name] <= high:
            raise ValueError("Camera display preference outside GUI range")
    for key, options in (("program_mode", {"Single point", "Dwell ramp array", "Uniform array"}),
                         ("program_spacing", {"Linear", "Logarithmic"}), ("cube_dark", {"none", "per_center", "per_frame"}),
                         ("sequence_measurement", {"Spectrum", "Intensity map", "Hyperspectral"})):
        if key in data and data[key] not in options:
            raise ValueError("Unknown experiment option: " + key)
    for key in ("program_first_s", "program_last_s"):
        if key in data and not 0 <= data[key] <= 43200:
            raise ValueError("Dwell preference outside GUI range")
    for key in ("sequence_cycles", "sequence_anneals", "sequence_measurements"):
        if key in data and not 1 <= data[key] <= 10000:
            raise ValueError("Repeat preference outside GUI range")
    for key in ("cube_x_points", "cube_y_points"):
        if key in data and not 1 <= data[key] <= 10000:
            raise ValueError("Cube point count outside GUI range")
    for key in ("cube_x_start", "cube_x_stop", "cube_y_start", "cube_y_stop"):
        if key in data and not -10 <= data[key] <= 10:
            raise ValueError("Cube coordinate outside GUI range")
    if "cube_settle" in data and not 0 <= data["cube_settle"] <= 60:
        raise ValueError("Cube settle outside GUI range")
    for key in ("sequence_spectrum_x", "sequence_spectrum_y"):
        if key in data and not -10 <= data[key] <= 10:
            raise ValueError("Sequence spectrum coordinate outside GUI range")
    if "sequence_spectrum_settle" in data and not 0 <= data["sequence_spectrum_settle"] <= 60:
        raise ValueError("Sequence spectrum settle outside GUI range")
    if any(key.startswith("focus_") for key in data):
        from labtools.runtime.focus_stack import FocusPlan

        text = data.get("focus_levels", "0")
        if len(text) > 4000:
            raise ValueError("Focus voltage list is too long")
        values = tuple(float(v.strip()) for v in text.replace(";", ",").split(",") if v.strip())
        if data.get("focus_direction", 0) not in (0, 1):
            raise ValueError("Invalid focus extension direction")
        FocusPlan(values, data.get("focus_sweeps", 1), data.get("focus_steps", 1),
                  1 if data.get("focus_direction", 0) == 0 else -1,
                  data.get("focus_settle", .5)).validate()
    return dict(data)
