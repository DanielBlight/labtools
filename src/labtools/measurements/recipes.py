"""Versioned data-only JSON recipes for implemented measurement facades."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.config.hyperspectral import HyperspectralConfig
from labtools.config.intensity_map import IntensityMapConfig
from labtools.config.spectrum import SpectrumSettings

from .alignment import AlignmentRequest
from .hyperspectral import HyperspectralRequest
from .intensity_map import IntensityMapRequest
from .spectrum import SpectrumRequest, load_dark, request_with_dark

RECIPE_SCHEMA_VERSION = 1
KINDS = {"spectrum", "dark", "alignment", "intensity_map", "hyperspectral"}


@dataclass(frozen=True)
class MeasurementRecipe:
    kind: str
    request: (
        SpectrumRequest | AlignmentRequest | IntensityMapRequest | HyperspectralRequest
    )
    dark_record_path: Path | None = None

    def validate(self) -> None:
        if self.kind not in KINDS:
            raise ValueError("Unsupported measurement recipe kind")
        self.request.validate()
        backend = self.backend
        if backend not in {"real", "simulation"}:
            raise ValueError("Recipe backend must be explicit")
        if self.kind == "spectrum" and self.request.dark_mode == "pre_taken":
            if self.dark_record_path is None and self.request.dark is None:
                raise ValueError(
                    "pre_taken spectrum recipe requires dark_record_path or in-memory dark"
                )
        elif (
            self.kind == "hyperspectral"
            and self.request.config.dark_mode == "pre_taken"
        ):
            if self.dark_record_path is None and self.request.dark is None:
                raise ValueError(
                    "pre_taken hyperspectral recipe requires dark_record_path"
                )
        elif self.dark_record_path is not None:
            raise ValueError("dark_record_path is only valid for pre_taken measurement")

    @property
    def backend(self) -> str:
        value = (
            self.request.settings
            if hasattr(self.request, "settings")
            else self.request.config
        )
        return value.backend


def _strict(cls, data: Any):
    if not isinstance(data, dict) or set(data) != {f.name for f in fields(cls)}:
        raise ValueError(f"{cls.__name__} fields must match exactly")
    return cls(**data)


def _jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def recipe_to_data(recipe: MeasurementRecipe) -> dict[str, Any]:
    recipe.validate()
    req = recipe.request
    if recipe.kind in {"spectrum", "dark"}:
        body = {"settings": _jsonable(asdict(req.settings)), "owner": req.owner}
        if recipe.kind == "spectrum":
            body.update(
                dark_mode=req.dark_mode,
                dark_record_path=str(recipe.dark_record_path)
                if recipe.dark_record_path
                else None,
            )
    elif recipe.kind == "alignment":
        body = {"settings": _jsonable(asdict(req.settings)), "owner": req.owner}
    elif recipe.kind == "hyperspectral":
        body = {
            "config": _jsonable(asdict(req.config)),
            "owner": req.owner,
            "output_path": str(req.output_path) if req.output_path else None,
            "dark_record_path": str(recipe.dark_record_path)
            if recipe.dark_record_path
            else None,
        }
    else:
        body = {
            "config": _jsonable(asdict(req.config)),
            "owner": req.owner,
            "resume_directory": str(req.resume_directory)
            if req.resume_directory
            else None,
        }
    return {
        "schema_version": RECIPE_SCHEMA_VERSION,
        "kind": recipe.kind,
        "recipe": body,
    }


def load_recipe(path: str | Path) -> MeasurementRecipe:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or set(data) != {"schema_version", "kind", "recipe"}:
        raise ValueError("Recipe requires only schema_version, kind and recipe")
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != RECIPE_SCHEMA_VERSION
    ):
        raise ValueError("Unsupported measurement recipe schema")
    kind = data["kind"]
    body = data["recipe"]
    if kind not in KINDS or not isinstance(body, dict):
        raise ValueError("Unsupported measurement recipe kind")
    if kind in {"spectrum", "dark"}:
        expected = {"settings", "owner"} | (
            {"dark_mode", "dark_record_path"} if kind == "spectrum" else set()
        )
        if set(body) != expected:
            raise ValueError("Recipe fields must match exactly")
        settings = _strict(SpectrumSettings, body["settings"])
        settings.validate()
        if kind == "dark":
            result = MeasurementRecipe(
                kind, SpectrumRequest(settings, owner=body["owner"])
            )
        else:
            dark_path = (
                Path(body["dark_record_path"]).expanduser().resolve()
                if body["dark_record_path"]
                else None
            )
            if body["dark_mode"] == "pre_taken":
                request = request_with_dark(
                    settings, load_dark(dark_path), owner=body["owner"]
                )
            else:
                request = SpectrumRequest(
                    settings, dark_mode=body["dark_mode"], owner=body["owner"]
                )
            result = MeasurementRecipe(kind, request, dark_path)
    elif kind == "alignment":
        if set(body) != {"settings", "owner"}:
            raise ValueError("Recipe fields must match exactly")
        result = MeasurementRecipe(
            kind,
            AlignmentRequest(
                _strict(AlignmentSettings, body["settings"]), body["owner"]
            ),
        )
    elif kind == "hyperspectral":
        if set(body) != {"config", "owner", "output_path", "dark_record_path"}:
            raise ValueError("Recipe fields must match exactly")
        raw = dict(body["config"])
        raw["spectrum"] = _strict(SpectrumSettings, raw["spectrum"])
        config = _strict(HyperspectralConfig, raw)
        output = (
            Path(body["output_path"]).expanduser().resolve()
            if body["output_path"]
            else None
        )
        dark_path = (
            Path(body["dark_record_path"]).expanduser().resolve()
            if body["dark_record_path"]
            else None
        )
        dark = load_dark(dark_path) if dark_path else None
        result = MeasurementRecipe(
            kind, HyperspectralRequest(config, output, dark, body["owner"]), dark_path
        )
    else:
        if set(body) != {"config", "owner", "resume_directory"}:
            raise ValueError("Recipe fields must match exactly")
        raw = dict(body["config"])
        raw["output_root"] = Path(raw["output_root"])
        raw["channels"] = tuple(raw["channels"])
        raw["channel_thresholds_v"] = tuple(raw["channel_thresholds_v"])
        raw["channel_edges"] = tuple(raw["channel_edges"])
        resume = (
            Path(body["resume_directory"]).expanduser().resolve()
            if body["resume_directory"]
            else None
        )
        result = MeasurementRecipe(
            kind,
            IntensityMapRequest(
                _strict(IntensityMapConfig, raw), resume, body["owner"]
            ),
        )
    result.validate()
    return result


def save_recipe(path: str | Path, recipe: MeasurementRecipe) -> None:
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(
            json.dumps(recipe_to_data(recipe), indent=2) + "\n", encoding="utf-8"
        )
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
