"""Read-only native-candidate inputs; reuse strict recipes and reviewed mirror profiles.

No native imports, device discovery, environment probing or execution permission.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from labtools.config.anneal_workspace import load_profile
from labtools.config.workspace import WorkspaceConfig
from labtools.measurements.recipes import load_recipe

REFERENCE_FIELDS = (
    "instrument_profile", "map_recipe", "spectrum_recipe", "device_selection_review",
    "wiring_review", "operating_limits_review", "native_environment_review", "optical_path_procedure",
)
RESOURCE_FIELDS = ("labjack", "counter", "spectrometer", "optical_path")
DISABLED_REASON = (
    "Native workspace execution is disabled in this candidate. Complete inputs do not enable it. "
    "Connected-device acceptance and an explicitly authorized execution integration remain required."
)


def _unique_object(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError(f"Duplicate JSON key: {key}")
        data[key] = value
    return data


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)


def _label(value):
    return isinstance(value, str) and bool(value.strip()) and value.strip() != "REVIEW-REQUIRED"


@dataclass(frozen=True)
class SourceStamp:
    field: str
    path: Path
    sha256: str


@dataclass(frozen=True)
class NativeCandidatePlan:
    """Validated values, not an approval or a device session."""

    configuration_id: str
    profile_id: str
    reservation_config: WorkspaceConfig
    map_config: object
    spectrum_request: object
    sources: tuple[SourceStamp, ...]
    hardware_settings: dict | None = None

    def verify_sources(self):
        for source in self.sources:
            if hashlib.sha256(source.path.read_bytes()).hexdigest() != source.sha256:
                raise ValueError(f"Candidate source changed since preflight: {source.field}")

    def describe(self):
        return {
            "configuration_id": self.configuration_id, "profile_id": self.profile_id,
            "hardware_settings": self.hardware_settings,
            "map_resources": list(self.reservation_config.map_resources),
            "spectrum_resources": list(self.reservation_config.spectrum_resources),
            "map_provider": "WorkspaceMapTransport / operation-scoped synchronous worker",
            "spectrum_provider": "WorkspaceSpectrumTransport / operation-scoped coroutine",
            "sources": [{"field": s.field, "path": str(s.path), "sha256": s.sha256} for s in self.sources],
        }


@dataclass(frozen=True)
class CandidatePreflight:
    errors: tuple[dict, ...]
    plan: NativeCandidatePlan | None = None
    runtime_inputs: tuple[str, ...] = ()

    def to_data(self):
        return {
            "inputs_complete": self.plan is not None and not self.errors,
            "execution_enabled": False, "disabled_reason": DISABLED_REASON,
            "hardware_opened": False, "environment_probed": False,
            "input_errors": list(self.errors),
            "runtime_inputs": list(self.runtime_inputs),
            "binding_plan": self.plan.describe() if self.plan is not None else None,
            "review_limit": "Referenced documents are present and hashed, not interpreted as physical approval.",
        }


def preflight_candidate(manifest_path):
    """Collect all missing inputs; never fill device settings from implicit defaults."""
    manifest_path = Path(manifest_path).expanduser().resolve()
    errors = []

    def issue(field, message):
        errors.append({"field": field, "message": message})

    try:
        data = _json(manifest_path)
        if isinstance(data, dict) and type(data.get("schema_version")) is int and data["schema_version"] == 2:
            from labtools.config.source_candidate import preflight_source_candidate

            return preflight_source_candidate(manifest_path, data)
        expected = {"schema_version", "configuration_id", "resources", *REFERENCE_FIELDS}
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError("Manifest fields must match the native-candidate template exactly")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("Unsupported native-candidate schema_version")
    except (OSError, ValueError, TypeError) as error:
        return CandidatePreflight(({"field": "manifest", "message": str(error)},))
    if not _label(data["configuration_id"]):
        issue("configuration_id", "Provide the reviewed map/spectrum candidate identity")
    resources = data["resources"]
    if not isinstance(resources, dict) or set(resources) != set(RESOURCE_FIELDS):
        issue("resources", "Provide exactly labjack, counter, spectrometer and optical_path resource identities")
        resources = dict.fromkeys(RESOURCE_FIELDS)
    for name in RESOURCE_FIELDS:
        if not _label(resources[name]):
            issue(f"resources.{name}", "Provide the reviewed physical-device or shared optical-path identity")
    if all(_label(value) for value in resources.values()) and len(set(resources.values())) != 4:
        issue("resources", "Use distinct resource identities; mirror/gate share labjack, workflows share optical_path")

    paths = {}
    stamps = [SourceStamp("manifest", manifest_path, hashlib.sha256(manifest_path.read_bytes()).hexdigest())]
    for field in REFERENCE_FIELDS:
        if not _label(data[field]):
            issue(field, "Provide a local reviewed source file reference, relative to the manifest or absolute")
            continue
        path = Path(data[field]).expanduser()
        path = (manifest_path.parent / path).resolve() if not path.is_absolute() else path.resolve()
        try:
            content = path.read_bytes()
            if not content.strip():
                raise ValueError("Referenced file is empty")
            paths[field] = path
            stamps.append(SourceStamp(field, path, hashlib.sha256(content).hexdigest()))
        except (OSError, ValueError) as error:
            issue(field, str(error))

    profile = mapping = spectrum = None
    for field, loader in (("instrument_profile", load_profile), ("map_recipe", load_recipe), ("spectrum_recipe", load_recipe)):
        if field not in paths:
            continue
        try:
            # Reject duplicate nested keys even though legacy loaders do not all do so.
            raw = _json(paths[field])
            if field == "spectrum_recipe" and isinstance(raw, dict):
                body = raw.get("recipe")
                if isinstance(body, dict) and (
                    body.get("dark_mode") != "none" or body.get("dark_record_path") is not None
                ):
                    raise ValueError("Candidate base recipe must use dark_mode=none and no dark archive")
            value = loader(paths[field])
            if field == "instrument_profile":
                profile = value
            elif field == "map_recipe":
                if value.kind != "intensity_map" or value.backend != "real":
                    raise ValueError("Require an existing strict intensity_map recipe with backend=real")
                if value.request.resume_directory is not None:
                    raise ValueError("Candidate map recipe must not contain a resume directory")
                mapping = value.request.config
            else:
                if value.kind != "spectrum" or value.backend != "real":
                    raise ValueError("Require an existing strict spectrum recipe with backend=real")
                if value.request.settings.configuration_id != data["configuration_id"]:
                    raise ValueError("Spectrum configuration_id does not match the candidate")
                if value.request.dark_mode != "none" or value.dark_record_path is not None:
                    raise ValueError("Candidate base recipe must use dark_mode=none; capture/load darks after acceptance")
                spectrum = value.request
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
            issue(field, str(error))

    if profile is not None and mapping is not None:
        if mapping.mirror_dio_pin != profile.mirror_dio_pin:
            issue("map_recipe.config.mirror_dio_pin", "Does not match the reviewed instrument profile")
        if (mapping.safe_voltage_min_v < profile.minimum_mirror_voltage_v
                or mapping.safe_voltage_max_v > profile.maximum_mirror_voltage_v):
            issue("map_recipe.config.safe_voltage_limits", "Map voltage envelope exceeds reviewed profile limits")
        if profile.home_x_voltage_v != 0 or profile.home_y_voltage_v != 0:
            issue("instrument_profile.home", "Existing map provider homes to zero; nonzero reviewed home is unsupported")
        if not mapping.safe_voltage_min_v <= 0 <= mapping.safe_voltage_max_v:
            issue("map_recipe.config.safe_voltage_limits", "Existing zero-voltage home must be inside the map envelope")
        if mapping.x_points * mapping.y_points > profile.maximum_total_points:
            issue("map_recipe.config.grid", "Grid exceeds the profile maximum_total_points")
    if mapping is not None:
        if not _label(mapping.time_controller_address):
            issue("map_recipe.config.time_controller_address", "Provide the reviewed counter address")
        if type(mapping.mirror_dio_pin) is not int or type(mapping.spad_gate_pin) is not int:
            issue("map_recipe.config.pins", "Mirror and gate pins must be explicit integers")
        elif mapping.spad_gate_pin in {mapping.mirror_dio_pin, mapping.mirror_dio_pin + 1}:
            issue("map_recipe.config.spad_gate_pin", "Gate overlaps the mirror's two I2C pins")
    if errors:
        return CandidatePreflight(tuple(errors))
    reservation = WorkspaceConfig(
        configuration_id=data["configuration_id"],
        resources=tuple(resources[name] for name in RESOURCE_FIELDS),
        map_resources=(resources["labjack"], resources["counter"], resources["optical_path"]),
        spectrum_resources=(resources["spectrometer"], resources["optical_path"]),
    )
    reservation.validate()
    return CandidatePreflight((), NativeCandidatePlan(
        data["configuration_id"], profile.profile_id, reservation, mapping, spectrum, tuple(stamps),
    ))
