"""Hardware-free recipe and profile tests."""

import json
from dataclasses import asdict, replace

import pytest

from labtools.config.anneal_workspace import (
    AnnealRecipe,
    InstrumentProfile,
    initialise_workspace,
    load_profile,
    load_recipe,
    save_recipe,
    validate_recipe,
)


def approved():
    return replace(InstrumentProfile(), approved=True, profile_id="test-only")


def recipe(tmp_path):
    return replace(AnnealRecipe(), output_root=str(tmp_path.resolve()))


def test_round_trip(tmp_path):
    original = recipe(tmp_path)
    path = tmp_path / "recipe.json"
    save_recipe(path, original)
    assert load_recipe(path) == original
    validate_recipe(original, approved())


@pytest.mark.parametrize(
    "change",
    [
        {"x_points": True},
        {"x_points": 0},
        {"x_start_v": float("nan")},
        {"x_stop_v": 6.0},
        {"maximum_open_time_s": 901.0},
        {"return_rotation_stage": False},
        {"anneal_rotation_coordinate": 1.0},
        {"output_root": "relative"},
        {"point_dwell_s": -1.0},
    ],
)
def test_invalid_recipe(tmp_path, change):
    with pytest.raises(ValueError):
        validate_recipe(replace(recipe(tmp_path), **change), approved())


def test_unknown_hardware_field(tmp_path):
    path = tmp_path / "bad.json"
    data = asdict(recipe(tmp_path))
    data["minimum_mirror_voltage_v"] = -100.0
    path.write_text(json.dumps({"schema_version": 1, "anneal": data}))
    with pytest.raises(ValueError):
        load_recipe(path)


def test_unapproved_profile(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(asdict(InstrumentProfile())))
    with pytest.raises(ValueError):
        load_profile(path)


def test_workspace_does_not_overwrite(tmp_path):
    initialise_workspace(tmp_path)
    with pytest.raises(FileExistsError):
        initialise_workspace(tmp_path)

def test_anneal_output_directory_collision_allocates_unique_suffix(
    tmp_path, monkeypatch
):
    from datetime import UTC, datetime

    import labtools.acquisition.laser_anneal as anneal_module

    fixed = datetime(2026, 11, 9, 16, 45, 0, tzinfo=UTC)

    class FixedDatetime:
        @classmethod
        def now(cls, tz):
            return fixed

    monkeypatch.setattr(anneal_module, "datetime", FixedDatetime)

    first = anneal_module._new_dir(tmp_path)
    second = anneal_module._new_dir(tmp_path)
    third = anneal_module._new_dir(tmp_path)

    assert first.name == "2026-11-09_16-45-00"
    assert second.name == "2026-11-09_16-45-00-001"
    assert third.name == "2026-11-09_16-45-00-002"
    assert first.is_dir() and second.is_dir() and third.is_dir()

