"""Explicit simulation workspace resource layout; no native imports or connections."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceConfig:
    configuration_id: str = "toy-scene-v1"
    backend: str = "simulation"
    resources: tuple[str, ...] = ("simulation-optical-path",)
    map_resources: tuple[str, ...] = ("simulation-optical-path",)
    spectrum_resources: tuple[str, ...] = ("simulation-optical-path",)
    simulation_seed: int = 0
    simulation_realtime: bool = True
    anneal_resources: tuple[str, ...] = ()
    camera_resources: tuple[str, ...] = ()

    def validate(self):
        if self.backend != "simulation":
            raise ValueError("Workspace supports simulation only; real hardware is not enabled")
        if not isinstance(self.configuration_id, str) or not self.configuration_id.strip():
            raise ValueError("configuration_id must be a nonempty string")
        for field in ("resources", "map_resources", "spectrum_resources"):
            names = getattr(self, field)
            if not isinstance(names, tuple) or not names or any(
                not isinstance(name, str) or not name.strip() for name in names
            ):
                raise ValueError(f"{field} must contain nonempty resource names")
            if len(set(names)) != len(names):
                raise ValueError(f"{field} contains duplicate resource names")
        for field in ("anneal_resources", "camera_resources"):
            names = getattr(self, field)
            if (not isinstance(names, tuple) or any(not isinstance(name, str) or not name.strip() for name in names)
                    or len(set(names)) != len(names)):
                raise ValueError(field + " must be a tuple of unique resource names")
        used = self.map_resources + self.spectrum_resources + self.anneal_resources + self.camera_resources
        if not set(used) <= set(self.resources):
            raise ValueError("Workflow resource names must exist in resources")
        if set(used) != set(self.resources):
            raise ValueError("Every declared resource must be used by a workflow")
        if type(self.simulation_seed) is not int or not 0 <= self.simulation_seed <= 2**32 - 1:
            raise ValueError("simulation_seed must be an integer in 0..4294967295")
        if type(self.simulation_realtime) is not bool:
            raise ValueError("simulation_realtime must be boolean")

    def for_workflow(self, owner):
        if owner == "Intensity map":
            return self.map_resources
        if owner == "Spectrum":
            return self.spectrum_resources
        if owner == "Annealing" and self.anneal_resources:
            return self.anneal_resources
        if owner == "Camera preview" and self.camera_resources:
            return self.camera_resources
        raise ValueError(f"Unknown workspace workflow: {owner}")


def load_workspace_config(path: Path) -> WorkspaceConfig:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate configuration key: {key}")
            result[key] = value
        return result

    data = json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
    expected = {"schema_version", "configuration_id", "backend", "resources", "map_resources",
                "spectrum_resources", "simulation_seed", "simulation_realtime"}
    if not isinstance(data, dict) or not expected <= set(data) <= expected | {"anneal_resources", "camera_resources"}:
        raise ValueError("Workspace configuration must contain exactly the documented schema fields")
    if type(data["schema_version"]) is not int or data.pop("schema_version") != 1:
        raise ValueError("Unsupported workspace schema_version")
    for field in ("anneal_resources", "camera_resources"):
        if field in data:
            if not isinstance(data[field], list):
                raise TypeError(field + " must be a JSON array")
            data[field] = tuple(data[field])
    for name in ("resources", "map_resources", "spectrum_resources"):
        if not isinstance(data[name], list):
            raise TypeError(f"{name} must be a JSON array")
        data[name] = tuple(data[name])
    config = WorkspaceConfig(**data)
    config.validate()
    return config
