import asyncio
import importlib
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

EXPECTED_EXPORTS = {
    "ExecutionStatus",
    "RealConfirmation",
    "RecipeExecutionReport",
    "execute_recipe",
    "execute_recipe_async",
    "MeasurementRuntime",
    "MeasurementRecipe",
    "load_recipe",
    "recipe_to_data",
    "save_recipe",
}


def test_public_exports_are_frozen_and_native_free():
    code = """
import sys
from labtools import measurements
expected = {
    "ExecutionStatus", "RealConfirmation", "RecipeExecutionReport",
    "execute_recipe", "execute_recipe_async", "MeasurementRuntime",
    "MeasurementRecipe", "load_recipe", "recipe_to_data", "save_recipe",
}
assert expected <= set(measurements.__all__)
forbidden = ("PyQt", "horiba_sdk", "uc480", "thorlabs_kinesis")
loaded = sorted(name for name in sys.modules if name.startswith(forbidden))
assert not loaded, loaded
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(
            os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src")
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_async_dispatch_and_immutable_report():
    from labtools.measurements import execute_recipe_async

    report = asyncio.run(
        execute_recipe_async("examples/measurements/recipes/alignment_simulation.json")
    )
    assert report.status == "success"
    assert report.backend == "simulation"
    assert report.configuration_id
    with pytest.raises(FrozenInstanceError):
        report.status = "failure"


def test_in_memory_dark_can_be_dispatched_without_a_persistence_path():
    from labtools.measurements import (
        MeasurementRecipe,
        execute_recipe,
        load_recipe,
        request_with_dark,
    )

    dark = execute_recipe("examples/measurements/recipes/dark_simulation.json").result
    base = load_recipe("examples/measurements/recipes/spectrum_simulation.json")
    request = request_with_dark(base.request.settings, dark, owner=base.request.owner)
    report = execute_recipe(MeasurementRecipe("spectrum", request))
    assert report.status == "success"


def test_failure_report_does_not_store_exception(monkeypatch):
    dispatch = importlib.import_module("labtools.measurements.dispatch")

    def fail(*args, **kwargs):
        raise RuntimeError("expected")

    monkeypatch.setattr(dispatch, "acquire_spectrum", fail)
    report = dispatch.execute_recipe(
        "examples/measurements/recipes/spectrum_simulation.json"
    )
    assert report.status == "failure"
    assert report.result is None
    assert report.error_type == "RuntimeError"
    assert not any(
        isinstance(value, BaseException) for value in report.__dict__.values()
    )
