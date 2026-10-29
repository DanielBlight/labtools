import builtins
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from labtools.config.spectrum import SpectrumSettings
from labtools.measurements import (
    MeasurementRecipe,
    SpectrumRequest,
    load_recipe,
    recipe_to_data,
    save_recipe,
)


def recipe():
    s = SpectrumSettings(
        "recipe-v1", "syncerity", 0.065, 0, 0, 0.1, 500, 510, backend="simulation"
    )
    return MeasurementRecipe("spectrum", SpectrumRequest(s, owner="recipe"))


def test_roundtrip_and_frozen(tmp_path):
    p = tmp_path / "r.json"
    save_recipe(p, recipe())
    loaded = load_recipe(p)
    assert loaded == recipe() and recipe_to_data(loaded)["schema_version"] == 1
    with pytest.raises(FrozenInstanceError):
        loaded.kind = "dark"


def test_overwrite_refused(tmp_path):
    p = tmp_path / "r.json"
    save_recipe(p, recipe())
    with pytest.raises(FileExistsError):
        save_recipe(p, recipe())


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(extra=1),
        lambda d: d.update(schema_version=2),
        lambda d: d.update(kind="anneal"),
        lambda d: d["recipe"].update(extra=1),
    ],
)
def test_rejects_unknown_schema_kind_fields(tmp_path, change):
    d = recipe_to_data(recipe())
    change(d)
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        load_recipe(p)


def test_data_only_no_qt_or_native_import(monkeypatch, tmp_path):
    old = builtins.__import__

    def guard(name, *a, **k):
        if name.startswith(("PyQt6", "horiba_sdk", "u6", "pyvisa", "zmq")):
            raise AssertionError(name)
        return old(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guard)
    p = tmp_path / "r.json"
    save_recipe(p, recipe())
    assert load_recipe(p).backend == "simulation"


def test_example_loads():
    p = Path("examples/measurements/recipes/spectrum_simulation.json")
    assert load_recipe(p).request.settings.configuration_id == "toy-scene-v1"
