"""Qt-free dispatch and typed reports for strict measurement recipes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from .alignment import acquire_alignment_frame, acquire_alignment_frame_async
from .hyperspectral import acquire_hyperspectral_map, acquire_hyperspectral_map_async
from .intensity_map import acquire_intensity_map, acquire_intensity_map_async
from .recipes import MeasurementRecipe, load_recipe
from .runtime import MeasurementRuntime
from .spectrum import (
    acquire_spectrum,
    acquire_spectrum_async,
    capture_dark,
    capture_dark_async,
)

RealConfirmation = Callable[[MeasurementRecipe], bool]
ExecutionStatus = Literal["success", "cancelled", "failure"]


@dataclass(frozen=True)
class RecipeExecutionReport:
    """Immutable execution outcome; exceptions are represented only as text."""

    recipe_kind: str
    backend: str
    configuration_id: str | None
    map_signature: Mapping[str, Any] | None
    started_at: datetime
    ended_at: datetime
    status: ExecutionStatus
    result: Any | None
    error_type: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None:
            raise ValueError("report timestamps must be timezone-aware")
        if self.ended_at < self.started_at:
            raise ValueError("report ended_at cannot precede started_at")
        if self.status == "success" and self.result is None:
            raise ValueError("successful report requires a result")
        if self.status == "failure" and self.result is not None:
            raise ValueError("failure report cannot carry a result")
        if self.map_signature is not None and not isinstance(
            self.map_signature, MappingProxyType
        ):
            object.__setattr__(
                self, "map_signature", MappingProxyType(dict(self.map_signature))
            )


def _recipe(value: MeasurementRecipe | str | Path) -> MeasurementRecipe:
    recipe = load_recipe(value) if isinstance(value, (str, Path)) else value
    if not isinstance(recipe, MeasurementRecipe):
        raise TypeError("recipe must be MeasurementRecipe or JSON path")
    recipe.validate()
    return recipe


def _confirm_real(
    recipe: MeasurementRecipe, confirm_real: RealConfirmation | None
) -> None:
    if recipe.backend != "real":
        return
    if confirm_real is None or confirm_real(recipe) is not True:
        raise PermissionError(
            "Real measurement recipe requires explicit caller confirmation"
        )


def _identity(recipe: MeasurementRecipe) -> tuple[str | None, Mapping[str, Any] | None]:
    if recipe.kind == "intensity_map":
        return None, MappingProxyType(
            dict(recipe.request.config.checkpoint_signature())
        )
    if recipe.kind == "hyperspectral":
        return recipe.request.config.configuration_id, None
    return recipe.request.settings.configuration_id, None


def _status(recipe: MeasurementRecipe, result: Any) -> ExecutionStatus:
    if recipe.kind == "intensity_map" and not result.result.complete:
        return "cancelled"
    if recipe.kind == "hyperspectral" and result.result.status == "cancelled":
        return "cancelled"
    return "success"


def _report(
    recipe: MeasurementRecipe, started: datetime, result: Any
) -> RecipeExecutionReport:
    configuration_id, map_signature = _identity(recipe)
    status = _status(recipe, result)
    return RecipeExecutionReport(
        recipe.kind,
        recipe.backend,
        configuration_id,
        map_signature,
        started,
        datetime.now(UTC),
        status,
        result,
    )


def _failure(
    recipe: MeasurementRecipe, started: datetime, exc: BaseException
) -> RecipeExecutionReport:
    configuration_id, map_signature = _identity(recipe)
    status: ExecutionStatus = (
        "cancelled" if isinstance(exc, asyncio.CancelledError) else "failure"
    )
    return RecipeExecutionReport(
        recipe.kind,
        recipe.backend,
        configuration_id,
        map_signature,
        started,
        datetime.now(UTC),
        status,
        None,
        type(exc).__name__,
        str(exc),
    )


def execute_recipe(
    value: MeasurementRecipe | str | Path,
    *,
    runtime: MeasurementRuntime | None = None,
    confirm_real: RealConfirmation | None = None,
    progress: Callable[[Any], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    timeout: float | None = None,
) -> RecipeExecutionReport:
    """Execute one supported recipe and return an immutable outcome report."""
    recipe = _recipe(value)
    _confirm_real(recipe, confirm_real)
    started = datetime.now(UTC)
    owned = runtime is None
    runtime = runtime or MeasurementRuntime(backend=recipe.backend)
    if runtime.backend != recipe.backend:
        if owned:
            runtime.close()
        raise ValueError("Recipe backend does not match MeasurementRuntime")
    try:
        if recipe.kind == "spectrum":
            result = acquire_spectrum(
                recipe.request,
                runtime=runtime.spectrum,
                timeout=timeout,
                progress=progress,
            )
        elif recipe.kind == "dark":
            result = capture_dark(
                recipe.request,
                runtime=runtime.spectrum,
                timeout=timeout,
                progress=progress,
            )
        elif recipe.kind == "alignment":
            result = acquire_alignment_frame(
                recipe.request,
                runtime=runtime.spectrum,
                timeout=timeout,
                progress=progress,
            )
        elif recipe.kind == "hyperspectral":
            result = acquire_hyperspectral_map(
                recipe.request,
                runtime=runtime.hyperspectral,
                progress=progress,
                cancel_requested=cancel_requested,
            )
        else:
            result = acquire_intensity_map(
                recipe.request,
                runtime=runtime.intensity_map,
                progress=progress,
                cancel_requested=cancel_requested,
            )
        return _report(recipe, started, result)
    except asyncio.CancelledError as exc:
        return _failure(recipe, started, exc)
    except Exception as exc:  # noqa: BLE001 - report boundary records ordinary failures
        return _failure(recipe, started, exc)
    finally:
        if owned:
            runtime.close()


async def execute_recipe_async(
    value: MeasurementRecipe | str | Path,
    *,
    runtime: MeasurementRuntime | None = None,
    confirm_real: RealConfirmation | None = None,
    progress: Callable[[Any], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> RecipeExecutionReport:
    """Asynchronously execute one recipe through the existing async facades."""
    recipe = _recipe(value)
    _confirm_real(recipe, confirm_real)
    started = datetime.now(UTC)
    owned = runtime is None
    runtime = runtime or MeasurementRuntime(backend=recipe.backend)
    if runtime.backend != recipe.backend:
        if owned:
            await asyncio.to_thread(runtime.close)
        raise ValueError("Recipe backend does not match MeasurementRuntime")
    try:
        if recipe.kind == "spectrum":
            result = await acquire_spectrum_async(
                recipe.request,
                runtime=runtime.spectrum,
                progress=progress,
                cancel_requested=cancel_requested,
            )
        elif recipe.kind == "dark":
            result = await capture_dark_async(
                recipe.request,
                runtime=runtime.spectrum,
                progress=progress,
                cancel_requested=cancel_requested,
            )
        elif recipe.kind == "alignment":
            result = await acquire_alignment_frame_async(
                recipe.request,
                runtime=runtime.spectrum,
                progress=progress,
                cancel_requested=cancel_requested,
            )
        elif recipe.kind == "hyperspectral":
            result = await acquire_hyperspectral_map_async(
                recipe.request,
                runtime=runtime.hyperspectral,
                progress=progress,
                cancel_requested=cancel_requested,
            )
        else:
            result = await acquire_intensity_map_async(
                recipe.request,
                runtime=runtime.intensity_map,
                progress=progress,
                cancel_requested=cancel_requested,
            )
        return _report(recipe, started, result)
    except asyncio.CancelledError as exc:
        return _failure(recipe, started, exc)
    except Exception as exc:  # noqa: BLE001 - report boundary records ordinary failures
        return _failure(recipe, started, exc)
    finally:
        if owned:
            await asyncio.to_thread(runtime.close)
