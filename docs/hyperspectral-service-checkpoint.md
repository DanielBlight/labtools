# Qt-free hyperspectral service checkpoint

The legacy `run_hyperspectral_scan.py` remains available for compatibility but is not the reviewed service. The new internal boundary comprises `HyperspectralConfig`, `HyperspectralService`, typed progress/result/provenance records, deterministic simulation, and pickle-free schema-version-1 NPZ persistence.

The service preserves legacy y-major/x-minor scan order and delegates every spectrum to `SpectrumService`; it does not duplicate range stitching, detector validation, or dark compatibility. The mirror context owns whole-operation reservations and cleanup. A borrowed spectrum service is never closed; an explicitly owned one is closed on service exit. Mirror factories must retain their `InstrumentSession` reservation until their context exits.

Cancellation is cooperative at point boundaries. Completed points remain marked in `completed_mask`; uncompleted cube elements are NaN. Archives refuse overwrite and are replaced atomically. Resume is not supported in version 1 because the intensity-map checkpoint signature cannot safely represent wavelength-axis and spectral-cube state.

Simulation uses the deterministic `gaussian-spatial-modulation-v1` scene applied to the existing synthetic `SpectrumService`. Provenance explicitly marks synthetic results and is not evidence of hardware, calibration, Qt, timing, or physical-policy acceptance.

This service is **not yet** a public `labtools.measurements` facade, recipe kind, dispatcher branch, `labtools measure` command, or GUI path. Multi-recipe pipelines and anneal dispatch remain unsupported.

## Source-checkout validation on Windows PowerShell

```powershell
uv run --no-sync python -m pytest -q tests/test_hyperspectral_service.py
uv run --no-sync python -m pytest -q
uv run --no-sync python -m ruff check src/labtools/config/hyperspectral.py src/labtools/acquisition/hyperspectral.py src/labtools/simulation/hyperspectral.py tests/test_hyperspectral_service.py
```

## Real-resource hardening boundary

`HyperspectralMirrorProvider` now holds the shared `mirror` reservation, which represents the scanning mirror and its backing LabJack, for the complete mirror context. Conflicts are rejected before the device factory opens. The current `InstrumentSession` does not own the HORIBA spectrometer, so this checkpoint deliberately does not claim an enforceable cross-service spectrometer reservation. `SpectrumService` remains the spectrometer owner and native imports remain lazy.

Acquisition failures now raise `HyperspectralAcquisitionError` from the original exception and carry the immutable failed partial result. Persistence and backend cleanup diagnostics remain attached without replacing the causal exception. Laser current, enable/disable, warm-up, shutter and optical-path confirmation remain responsibilities of a future higher-level hazardous physical workflow.

## Operation-scoped HORIBA ownership

`SpectrumService.operation(settings)` now opens one configured range backend and lends a validation-preserving service across the complete cube. The real range adapter owns a process-local exclusive lock for exactly the lifetime of the actual HORIBA instance; a competing operation is rejected before native construction. Standalone SpectrumService calls retain their existing open/acquire/close lifecycle. `open_hyperspectral_service` validates and checks cancellation before resources open, acquires the mirror reservation first, then owns the persistent spectrum backend, and lends both to `HyperspectralService`.

## Failure-matrix acceptance

Focused offline failure injection now covers first-point and mid-scan mirror and spectrum failures, wavelength-axis drift, cancellation after completed data, immutable failed/cancelled partial results, borrowed/owned close counts, owned-close diagnostics, and unwrapped `KeyboardInterrupt`. Existing HORIBA wrapper tests remain authoritative for factory/connect/configure/disconnect cleanup and lock release. These tests are offline evidence only.
