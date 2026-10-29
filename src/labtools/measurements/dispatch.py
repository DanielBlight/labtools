"""Qt-free dispatcher for strict, data-only measurement recipes."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .alignment import acquire_alignment_frame
from .intensity_map import acquire_intensity_map
from .recipes import MeasurementRecipe, load_recipe
from .runtime import MeasurementRuntime
from .spectrum import acquire_spectrum, capture_dark

RealConfirmation = Callable[[MeasurementRecipe], bool]


def _recipe(value: MeasurementRecipe | str | Path) -> MeasurementRecipe:
    recipe = load_recipe(value) if isinstance(value, (str, Path)) else value
    if not isinstance(recipe, MeasurementRecipe):
        raise TypeError("recipe must be MeasurementRecipe or JSON path")
    recipe.validate()
    return recipe


def _confirm_real(recipe: MeasurementRecipe, confirm_real: RealConfirmation | None) -> None:
    if recipe.backend != "real":
        return
    if confirm_real is None or confirm_real(recipe) is not True:
        raise PermissionError("Real measurement recipe requires explicit caller confirmation")


def execute_recipe(
    value: MeasurementRecipe | str | Path,
    *,
    runtime: MeasurementRuntime | None = None,
    confirm_real: RealConfirmation | None = None,
    progress: Callable[[Any], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    timeout: float | None = None,
):
    """Execute one supported recipe through its existing facade."""
    recipe = _recipe(value)
    _confirm_real(recipe, confirm_real)
    owned = runtime is None
    runtime = runtime or MeasurementRuntime(backend=recipe.backend)
    if runtime.backend != recipe.backend:
        raise ValueError("Recipe backend does not match MeasurementRuntime")
    try:
        if recipe.kind == "spectrum":
            return acquire_spectrum(recipe.request, runtime=runtime.spectrum, timeout=timeout, progress=progress)
        if recipe.kind == "dark":
            return capture_dark(recipe.request, runtime=runtime.spectrum, timeout=timeout, progress=progress)
        if recipe.kind == "alignment":
            return acquire_alignment_frame(recipe.request, runtime=runtime.spectrum, timeout=timeout, progress=progress)
        if recipe.kind == "intensity_map":
            return acquire_intensity_map(recipe.request, runtime=runtime.intensity_map, progress=progress, cancel_requested=cancel_requested)
        raise ValueError("Unsupported measurement recipe kind")
    finally:
        if owned:
            runtime.close()
