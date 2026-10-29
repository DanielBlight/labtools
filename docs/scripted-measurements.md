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
