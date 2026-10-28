"""Strict JSON recipes, instrument profiles and anneal policy validation.

No hardware is imported until build_config is called. Validation and workspace
creation never connect to devices. Filesystem permissions protect the profile;
this module is not a security boundary against arbitrary Python execution.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, fields, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


@dataclass(frozen=True)
class AnnealRecipe:
    x_start_v: float = -1.0
    x_stop_v: float = 1.0
    x_points: int = 2
    y_start_v: float = 1.0
    y_stop_v: float = 3.0
    y_points: int = 2
    passes: int = 1
    point_dwell_s: float = 0.001
    mirror_settle_s: float = 0.0
    serpentine: bool = False
    anneal_rotation_coordinate: float = 35000.0
    return_rotation_coordinate: float = 90000.0
    return_rotation_stage: bool = True
    maximum_open_time_s: float = 900.0
    save_run_log: bool = True
    output_root: str = ""


@dataclass(frozen=True)
class InstrumentProfile:
    profile_id: str = "REVIEW-REQUIRED"
    approved: bool = False
    sc10_port: str = "COM4"
    sc10_baud_rate: int = 9600
    sc10_timeout_s: float = 0.5
    mirror_dio_pin: int = 2
    minimum_mirror_voltage_v: float = -5.0
    maximum_mirror_voltage_v: float = 5.0
    home_x_voltage_v: float = 0.0
    home_y_voltage_v: float = 0.0
    rotation_stage_timeout_s: float = 60.0
    rotation_min_coordinate: float = 35000.0
    rotation_max_coordinate: float = 90000.0
    maximum_open_time_s: float = 900.0
    maximum_total_points: int = 1000000
    require_return_stage: bool = True


def profile_path() -> Path:
    override = os.environ.get("LABTOOLS_INSTRUMENT_PROFILE")
    if override:
        return Path(override).expanduser().resolve()
    root = Path(os.environ.get("PROGRAMDATA", str(Path.home() / ".config")))
    return root / "Labtools" / "instrument.json"


def _strict(cls, data):
    if not isinstance(data, dict):
        raise ValueError(  # noqa: TRY004 - invalid serialized configuration structure
            "Expected a JSON object"
        )
    defaults = asdict(cls())
    unknown = set(data) - set(defaults)
    if unknown:
        raise ValueError("Unknown fields: " + ", ".join(sorted(unknown)))
    for key, value in data.items():
        expected = defaults[key]
        if isinstance(expected, bool):
            valid = type(value) is bool
        elif isinstance(expected, int):
            valid = type(value) is int
        elif isinstance(expected, float):
            valid = type(value) in (int, float) and math.isfinite(value)
        else:
            valid = isinstance(value, str)
        if not valid:
            raise ValueError(f"Invalid type or non-finite value for {key}")
    return cls(**data)


def load_profile(path: Path | None = None) -> InstrumentProfile:
    path = path or profile_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(
            f"Instrument profile missing: {path}. Ask the maintainer to install it."
        ) from exc
    if not isinstance(data, dict) or set(data) != {
        field.name for field in fields(InstrumentProfile)
    }:
        raise ValueError(
            "Instrument profile must explicitly specify every field; use the maintainer template"
        )
    return validate_profile(_strict(InstrumentProfile, data))


def validate_profile(profile):
    _strict(InstrumentProfile, asdict(profile))
    if (
        not profile.approved
        or not profile.profile_id.strip()
        or profile.profile_id == "REVIEW-REQUIRED"
    ):
        raise ValueError(
            "The instrument profile must be reviewed and approved by the maintainer."
        )
    if profile.minimum_mirror_voltage_v >= profile.maximum_mirror_voltage_v:
        raise ValueError("Invalid mirror voltage limits")
    if profile.rotation_min_coordinate > profile.rotation_max_coordinate:
        raise ValueError("Invalid rotation-stage limits")
    for key in (
        "sc10_timeout_s",
        "rotation_stage_timeout_s",
        "maximum_open_time_s",
        "maximum_total_points",
        "sc10_baud_rate",
    ):
        if getattr(profile, key) <= 0:
            raise ValueError(f"Profile {key} must be positive")
    if profile.mirror_dio_pin < 0 or not profile.sc10_port.strip():
        raise ValueError("Invalid instrument connection settings")
    for value in (profile.home_x_voltage_v, profile.home_y_voltage_v):
        if (
            not profile.minimum_mirror_voltage_v
            <= value
            <= profile.maximum_mirror_voltage_v
        ):
            raise ValueError("Home coordinate exceeds mirror limits")
    return profile


def validate_recipe(recipe: AnnealRecipe, profile: InstrumentProfile) -> None:
    _strict(AnnealRecipe, asdict(recipe))
    validate_profile(profile)
    if min(recipe.x_points, recipe.y_points, recipe.passes) < 1:
        raise ValueError("Point counts and passes must be positive integers")
    if min(recipe.point_dwell_s, recipe.mirror_settle_s) < 0:
        raise ValueError("Dwell and settle cannot be negative")
    total = recipe.x_points * recipe.y_points * recipe.passes
    if total > profile.maximum_total_points:
        raise ValueError("Recipe exceeds instrument point-count limit")
    for key in ("x_start_v", "x_stop_v", "y_start_v", "y_stop_v"):
        if (
            not profile.minimum_mirror_voltage_v
            <= getattr(recipe, key)
            <= profile.maximum_mirror_voltage_v
        ):
            raise ValueError(f"{key} exceeds instrument voltage limits")
    for key in ("anneal_rotation_coordinate", "return_rotation_coordinate"):
        validate_stage_coordinate(getattr(recipe, key), profile)
    if profile.require_return_stage and not recipe.return_rotation_stage:
        raise ValueError("This instrument requires returning the rotation stage")
    if not 0 < recipe.maximum_open_time_s <= profile.maximum_open_time_s:
        raise ValueError("Requested maximum open time exceeds the instrument limit")
    estimate = total * (recipe.point_dwell_s + recipe.mirror_settle_s)
    if estimate > recipe.maximum_open_time_s:
        raise ValueError("Estimated dwell/settle time exceeds requested maximum")
    if not recipe.output_root or not Path(recipe.output_root).is_absolute():
        raise ValueError("output_root must be an absolute path")


def validate_stage_coordinate(coordinate, profile=None):
    profile = profile or load_profile()
    if type(coordinate) not in (int, float) or not math.isfinite(coordinate):
        raise ValueError("Invalid rotation coordinate")
    if (
        not profile.rotation_min_coordinate
        <= coordinate
        <= profile.rotation_max_coordinate
    ):
        raise ValueError("Rotation coordinate exceeds instrument limits")


def load_recipe(path: Path) -> AnnealRecipe:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or set(data) != {"schema_version", "anneal"}:
        raise ValueError("Recipe requires only schema_version and anneal")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported recipe schema")
    return _strict(AnnealRecipe, data["anneal"])


def save_recipe(path: Path, recipe: AnnealRecipe) -> None:
    _strict(AnnealRecipe, asdict(recipe))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"schema_version": 1, "anneal": asdict(recipe)}, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def recipe_from_config(config) -> AnnealRecipe:
    data = {field.name: getattr(config, field.name) for field in fields(AnnealRecipe)}
    data["output_root"] = str(data["output_root"])
    return _strict(AnnealRecipe, data)


def _resolved_values(recipe, profile):
    validate_recipe(recipe, profile)
    data = asdict(recipe)
    data["output_root"] = Path(recipe.output_root)
    for key in (
        "sc10_port",
        "sc10_baud_rate",
        "sc10_timeout_s",
        "mirror_dio_pin",
        "minimum_mirror_voltage_v",
        "maximum_mirror_voltage_v",
        "home_x_voltage_v",
        "home_y_voltage_v",
        "rotation_stage_timeout_s",
    ):
        data[key] = getattr(profile, key)
    data["instrument_profile_id"] = profile.profile_id
    data["instrument_profile_sha256"] = hashlib.sha256(
        json.dumps(asdict(profile), sort_keys=True).encode()
    ).hexdigest()
    try:
        data["software_version"] = version("lab-tools")
    except PackageNotFoundError:
        data["software_version"] = "uninstalled"
    return data


def build_config(recipe, profile=None):
    from labtools.acquisition.laser_anneal import LaserAnnealConfig

    return LaserAnnealConfig(**_resolved_values(recipe, profile or load_profile()))


def resolve_gui_config(config):
    return replace(
        config, **_resolved_values(recipe_from_config(config), load_profile())
    )


def validate_run_config(config):
    profile = load_profile()
    expected = _resolved_values(recipe_from_config(config), profile)
    for key, value in expected.items():
        if getattr(config, key) != value:
            raise ValueError(
                f"Configuration {key} does not match the instrument profile; use build_config()."
            )
    config.validate()


def initialise_workspace(root: Path):
    root = Path(root).expanduser().resolve()
    (root / "recipes").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    path = root / "recipes" / "anneal.json"
    if path.exists():
        raise FileExistsError(f"Will not overwrite {path}")
    save_recipe(path, replace(AnnealRecipe(), output_root=str(root / "data")))
    return path
