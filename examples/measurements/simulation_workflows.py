"""End-to-end simulation workflows sharing one MeasurementRuntime."""

from __future__ import annotations

from pathlib import Path

from labtools.measurements import (
    MeasurementRecipe,
    MeasurementRuntime,
    execute_recipe,
    load_recipe,
    request_from_resume,
    request_with_dark,
)

ROOT = Path(__file__).resolve().parent
RECIPES = ROOT / "recipes"

with MeasurementRuntime(backend="simulation") as runtime:
    dark_report = execute_recipe(RECIPES / "dark_simulation.json", runtime=runtime)
    spectrum_recipe = load_recipe(RECIPES / "spectrum_simulation.json")
    spectrum_request = request_with_dark(
        spectrum_recipe.request.settings,
        dark_report.result,
        owner=spectrum_recipe.request.owner,
    )
    spectrum_report = execute_recipe(
        MeasurementRecipe("spectrum", spectrum_request), runtime=runtime
    )

    alignment_report = execute_recipe(
        RECIPES / "alignment_simulation.json", runtime=runtime
    )

    snapshots = 0

    def stop_after_first(_snapshot) -> None:
        global snapshots
        snapshots += 1

    stopped_report = execute_recipe(
        RECIPES / "intensity_map_simulation.json",
        runtime=runtime,
        progress=stop_after_first,
        cancel_requested=lambda: snapshots >= 1,
    )
    resume_request = request_from_resume(
        stopped_report.result.result.output_directory,
        owner="scripted-map-resume-example",
    )
    resumed_report = execute_recipe(
        MeasurementRecipe("intensity_map", resume_request), runtime=runtime
    )

print(spectrum_report.status, alignment_report.status, resumed_report.status)
