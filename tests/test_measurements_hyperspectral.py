from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import numpy as np
import pytest

from labtools.config.hyperspectral import HyperspectralConfig
from labtools.config.spectrum import SpectrumSettings
from labtools.measurements import (
    HyperspectralRequest,
    acquire_hyperspectral_map,
    acquire_hyperspectral_map_async,
)
from labtools.measurements.dispatch import execute_recipe, execute_recipe_async
from labtools.measurements.recipes import load_recipe, recipe_to_data


def request(output=None):
    s = SpectrumSettings(
        "public-hyper-v1", "syncerity", 0.1, 2, 0, 0.5, 500, 600, backend="simulation"
    )
    return HyperspectralRequest(
        HyperspectralConfig("public-hyper-v1", s, 0, 1, 2, 0, 1, 2), output
    )


def test_sync_async_and_provenance(tmp_path):
    a = acquire_hyperspectral_map(request())
    b = asyncio.run(acquire_hyperspectral_map_async(request(tmp_path / "cube.npz")))
    assert np.array_equal(a.result.intensity, b.result.intensity)
    assert a.result.intensity.shape == (2, 2, 64)
    assert a.provenance.synthetic and a.provenance.scan_order == "y-major/x-minor"
    assert b.result.output_path == tmp_path / "cube.npz"


def test_cancelled_partial():
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls > 3

    value = acquire_hyperspectral_map(request(), cancel_requested=cancel)
    assert value.result.status == "cancelled"
    assert not value.result.intensity.flags.writeable


def test_recipe_dispatch_sync_async(tmp_path):
    data = {
        "schema_version": 1,
        "kind": "hyperspectral",
        "recipe": {
            "config": {
                **request().config.__dict__,
                "spectrum": request().config.spectrum.__dict__,
            },
            "owner": "recipe",
            "output_path": None,
            "dark_record_path": None,
        },
    }
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(data))
    recipe = load_recipe(path)
    assert recipe_to_data(recipe)["kind"] == "hyperspectral"
    a = execute_recipe(recipe)
    b = asyncio.run(execute_recipe_async(recipe))
    assert a.status == b.status == "success"
    assert a.configuration_id == "public-hyper-v1"


def test_unknown_recipe_field_rejected(tmp_path):
    data = {
        "schema_version": 1,
        "kind": "hyperspectral",
        "recipe": {
            "config": {},
            "owner": "x",
            "output_path": None,
            "dark_record_path": None,
            "resume": True,
        },
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_recipe(path)


def test_import_isolation():
    code = """import sys,labtools.measurements; blocked=[n for n in sys.modules if n.startswith(('PyQt','labtools.devices','horiba_sdk','u6'))]; assert not blocked,blocked"""
    subprocess.run([sys.executable, "-c", code], check=True)
