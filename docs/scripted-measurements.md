# Scriptable measurements target architecture

Operators should automate repeatable work by importing stable **measurement functions**, not device wrappers or GUI classes. The target public namespace is `labtools.measurements`, with one function per scientific workflow: `acquire_spectrum`, `capture_dark`, `acquire_alignment_frame`, `acquire_intensity_map`, `acquire_hyperspectral_map`, and `run_anneal_recipe`. Each accepts an immutable validated request and an explicit runtime/session, returns an immutable result or dataset reference, and uses the same acquisition/service implementation as the GUI.

## Required layering

- `config/`: frozen validated request/recipe types, units in names, explicit `backend` and reviewed configuration/profile IDs.
- `measurements/`: thin stable public facade. No Qt, plots, dialogs, SDK imports or duplicated acquisition loops.
- `acquisition/`: authoritative workflow algorithms, progress/cancellation/checkpoint/resume.
- `runtime/`: `InstrumentSession`, service factories, resource reservations and real/simulation composition.
- `devices/`: transport wrappers, not the operator scripting API.
- `io/`: explicit save/load/export helpers. Measurement calls return data; they do not silently choose output paths unless the workflow is intrinsically dataset-backed.

Do not create a second implementation called “measurements”. The facade delegates to existing `SpectrumService` and `acquire_intensity_map`; future hyperspectral work should first become a reviewed acquisition service rather than exporting the unsafe legacy runner. GUI controllers must call the same facade or service contract.

## Proposed usage

```python
from labtools.measurements import MeasurementRuntime, acquire_spectrum
from labtools.config.spectrum import SpectrumSettings

settings = SpectrumSettings(
    configuration_id="REVIEWED-ID",
    preset="syncerity",
    exposure_s=0.1,
    gain=2,
    speed=0,
    slit_width_mm=0.5,
    start_nm=500.0,
    end_nm=600.0,
    backend="real",
)

with MeasurementRuntime.from_profile() as runtime:
    result = acquire_spectrum(runtime, settings, dark_mode="per_center")
```

`MeasurementRuntime` is a planned convenience owner around session/services, not implemented by this checkpoint. It must reject conflicting reservations, close deterministically, expose explicit real/simulation provenance, and never turn an approved profile into a physical-safety claim. Long jobs need progress and cooperative cancellation callbacks. Hazardous workflows retain explicit safety acknowledgements outside reusable recipe files.

## Delivery plan

1. Freeze naming, request/result protocols, provenance and exception contracts with native-free contract tests.
2. Add `labtools.measurements.spectrum` as a thin facade over `SpectrumService`, including a synchronous convenience function that owns one worker/runtime and an async API for advanced scripts.
3. Add intensity-map facade over the existing resumable acquisition without changing schema/signatures.
4. Convert hyperspectral mapping from the legacy runner into validated acquisition/service logic with simulation, cleanup and dataset provenance before public export.
5. Add anneal facade only after hazardous workflow acceptance; keep safety confirmation external and non-persisted.
6. Add versioned JSON recipes and examples per measurement. Scripts may compose measurements in Python, while editable recipes remain data-only.
7. Publish an API compatibility policy, generated reference, simulation examples and end-to-end tests proving GUI/script parity.

Until these phases land, use the existing `SpectrumService`, `SpectrumSettings`, `acquire_intensity_map`, and the anneal recipe runner directly as documented examples. Do not import GUI modules or use the legacy hyperspectral runner for unattended work.

## Implemented spectrum facade checkpoint

`labtools.measurements` now exports frozen `SpectrumRequest`, `MeasurementProvenance`, `SpectrumMeasurement`, explicit `SpectrumRuntime`, and sync/async `acquire_spectrum` functions. It delegates to `SpectrumService`/`SpectrumWorker`; it does not duplicate range acquisition. Backend and reviewed configuration ID are preserved in provenance, simulation is explicitly marked synthetic, progress reports started/completed, and cancellation uses existing cooperative service boundaries. Runtime ownership is explicit: omitted runtime is owned and closed by the function; supplied runtime remains caller-owned and reusable.

See `examples/measurements/simulate_spectrum.py`. Detector minima remain enforced by existing settings/backend validation. Map, hyperspectral and anneal facades remain unimplemented.

## Dark capture and reuse

The spectrum facade now exports `capture_dark`, `capture_dark_async`, `save_dark`, `load_dark`, and `request_with_dark`. Dark records remain the existing immutable `DarkRecord`; persistence delegates to schema-version-1 pickle-free NPZ. Reuse requires exact `SpectrumSettings` equality, including reviewed configuration ID and backend, before acquisition.

## Alignment-frame facade

The public package now exports frozen `AlignmentRequest`/`AlignmentMeasurement` plus synchronous and async `acquire_alignment_frame` entry points. They delegate to the existing `SpectrumWorker.acquire_alignment` and `SpectrumService.acquire_alignment`, preserve configuration/backend provenance, detector minima, raw/corrected immutable arrays, actual centre readback, progress and cooperative cancellation.

## Intensity-map facade

`labtools.measurements` now exports frozen `IntensityMapRequest`, `IntensityMapProvenance`, `IntensityMapMeasurement`, explicit `IntensityMapRuntime`, sync/async acquisition and `request_from_resume`. The facade delegates unchanged to `acquisition.acquire_intensity_map`; schema 1, checkpoint signatures, output directory, progress snapshots, cancellation checkpoints and deterministic `gaussian-scene-v1` simulation remain authoritative there.

## Unified measurement runtime

`MeasurementRuntime` now lazily composes the existing `SpectrumRuntime` and `IntensityMapRuntime` for sequential scripted workflows. It does not merge their ownership models: spectrum continues to own its service/worker, while map composition continues to use its provider/application and `InstrumentSession` reservations. Injected runtimes are borrowed and never closed; lazily created runtimes are owned and independently closed. Backend identity is shared and explicit. Native imports remain deferred until the child runtime or real backend is used.

## Versioned measurement recipes

Schema-version-1 JSON recipes are now available for the implemented `spectrum`, `dark`, `alignment`, and `intensity_map` facades. Loading is strict and data-only: the root and kind-specific fields must match exactly; unknown fields and schema/kind changes are rejected. Recipes preserve explicit backend, reviewed spectrum/alignment configuration IDs, unit-bearing field names, map schema-compatible configuration, optional map resume directory, and an optional pre-taken dark NPZ path. A pre-taken dark is loaded through the existing pickle-free NPZ reader and must exactly match the spectrum settings before the recipe is returned.

Examples are under `examples/measurements/recipes/`. Use `load_recipe(path)` and dispatch only on the returned `kind`; recipe loading never executes Python or imports Qt/native SDK modules.

## Recipe dispatch

`execute_recipe` dispatches one strict recipe to the existing spectrum, dark, alignment or intensity-map facade. Simulation executes without confirmation. A real recipe requires a caller-supplied confirmation callback returning exactly `True` before a runtime or backend is created. The dispatcher borrows a supplied `MeasurementRuntime` or owns/closes a temporary one, forwards progress/cancellation, and returns the existing immutable result type. It does not sequence multiple recipes or execute recipe-provided code.

## Production-ready single-recipe execution

`execute_recipe` and `execute_recipe_async` support exactly one schema-version-1
`spectrum`, `dark`, `alignment`, or `intensity_map` recipe. Both return an
immutable `RecipeExecutionReport` with UTC timestamps, backend, configuration ID
or map checkpoint signature, status, and the immutable facade result when one
exists. Failures record only exception type and message strings; exception
objects are never placed in the report.

The operator CLI validates without opening hardware:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python -m labtools.cli measure validate .\examples\measurements\recipes\spectrum_simulation.json
uv run --no-sync python -m labtools.cli measure run .\examples\measurements\recipes\spectrum_simulation.json
```

A real recipe is never executed unless `--confirm-real` is present on that exact
`measure run` invocation. There is no prompt, environment-variable override, or
recipe field that bypasses the flag. The flag confirms intent to execute only;
it is not evidence that the optical path, sample, detector, stages, shutter, or
other physical conditions are safe.

Recipe paths are expanded and resolved from the current PowerShell working
directory. Paths stored inside a recipe retain the strict schema behavior already
documented. Use absolute paths in operator-managed recipes when the working
directory is not controlled.

For shared-runtime simulation of dark capture and spectrum reuse, alignment, and
a deliberately stopped then resumed intensity map, run:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python .\examples\measurements\simulation_workflows.py
```

Cancellation is cooperative. Spectrum, dark, and alignment cancellation is
reported as `cancelled`; an intensity map returns its immutable stopped result so
the checkpoint output directory can be used for resume. Always close a borrowed
`MeasurementRuntime` with a `with` block. An internally owned runtime is closed
by dispatch even after cancellation or failure.

Reports preserve execution provenance; they do not serialize exception objects
or large result arrays for the CLI. Dataset and dark-record persistence continue
to use their existing explicit save/load APIs.

This interface deliberately does not support multi-recipe pipelines,
hyperspectral acquisition, or laser annealing. Hyperspectral requires a reviewed
service/refactor first. Annealing remains a hazardous workflow with separate
physical confirmation and acceptance requirements.

## Hyperspectral status

A reviewed internal Qt-free service now exists, but it is not exported from `labtools.measurements`, accepted by strict recipes or dispatch, or exposed through `labtools measure`. Use it only for service-level development and offline simulation until the next acceptance checkpoint.
