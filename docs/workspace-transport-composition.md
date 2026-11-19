# Integrated fake-transport workspace candidate

This batch composes both existing transport boundaries in one configured operator
workspace, with a headless end-to-end rehearsal and one Qt acceptance test. It replaces
separate adapter-only iterations with a single integration milestone. No real controls,
factory import paths, device addresses or native approval are exposed by the new mode.

## Use

```powershell
uv run --no-sync labtools simulate workspace --transport-contracts --config examples/workspace/simulation.json
```

The normal simulation launcher is unchanged when the flag is omitted. The new flag
injects one fixed FakeTransportComposition into the existing map/spectrum panels,
binds to their existing ownership object and labels the window FAKE TRANSPORT CONTRACTS.

The existing native-contract adapters execute with fixed fake LabJack/counter/mirror/
gate/spectrometer transports wrapping the existing synthetic models. No new scene or
second reservation registry is added. Internal provider settings are real-contract
labels only; outer requests, dark records, results, checkpoints, CSV/NPZ/PNG metadata
remain simulation/synthetic. This avoids mislabelling fake data as experimental.

One optional stitcher callback is threaded through the existing range acquisition,
real range adapter and spectrum boundary. Default None preserves the existing SDK
stitching path. The fake mode supplies an explicit one-centre filter, not a vendor SDK
replacement or proof of stitching correctness. It does not monkeypatch global modules.

Services are reused; handles are constructed and closed per operation on the original
map worker or spectrum coroutine thread/loop. The existing InstrumentSession remains
the sole reservation authority. No native handle is submitted to its executor.
Bounded trace/fault helpers are diagnostics, not locks or a device registry.

## One local validation pass

```powershell
uv run --no-sync ruff check --fix src/labtools/acquisition/range_spectrum.py src/labtools/runtime/spectrum_backend.py src/labtools/runtime/workspace_spectrum_transport.py src/labtools/simulation/workspace.py src/labtools/simulation/transport_fakes.py src/labtools/simulation/transport_composition.py tests/test_workspace_transport_composition.py
uv run --no-sync pytest -q -ra tests/test_workspace_transport_composition.py tests/test_workspace_map_transport.py tests/test_workspace_spectrum_transport.py tests/test_spectrum_service.py tests/test_intensity_map_simulation.py
```

The new Qt test runs the actual existing panels with both fake-transport boundaries:
map complete/cancel/resume, cross-tab conflict, close during acquisition, map and
spectrum fault/recovery, dark save/load/subtraction, repeat, synthetic output metadata,
thread/loop affinity and grid memory. Native imports are forbidden in its subprocess.
A missing Qt runtime is a skip and remains an acceptance gap, not success.

Sandbox result: 112 passed, 1 skipped, 236 plotting-library deprecation warnings in
119.10s across the focused selection before adding the CLI-construction test. That
additional test passed separately (1 passed in 24.40s). Ruff 0.17.4 check --fix passed
on all changed Python paths. The actual Qt test is blocked by missing libGL.so.1 in
the sandbox; PyQt6 was installed but its Widgets runtime could not load. No Qt success
is claimed. No user-PC dependency changes are required by this delivery.

## Headless acceptance/recovery rehearsal

```powershell
uv run --no-sync labtools simulate workspace --rehearse-transports --config examples/workspace/simulation.json
```

This uses the same composition, not a second implementation. It creates a unique
SIMULATION/transport-rehearsal-* folder beneath the selected --output root and records
rehearsal.json, synthetic marker, map outputs and raw/corrected/dark spectrum archives.
Ten checks cover map completion, configured conflicts, stop/resume equality, map fault
recovery, dark archive/subtraction/repeat, spectrum cancellation/fault recovery,
synthetic archive provenance, released leases and per-handle affinity. A failed check
records failed status and raises; assertions are not used for these acceptance gates.

This rehearsal actually passed in the sandbox. It is available for convenient repeat
use after future relevant changes, not an instruction to rerun already accepted work.
Its small fixture fits the 4096-event trace; that bounded trace is not a complete
long-running audit. Fake timing/electronics and vendor stitching remain unvalidated.

## Visual acceptance

In the flagged workspace, complete a small map, switch to Spectrum, acquire raw,
capture/save/load a dark, subtract and repeat. Confirm synthetic plots/files. Start a
larger map (.02 s integration, e.g. 20x20), try Spectrum to see conflict rejection,
then Stop all and resume. Close during acquisition and again after Ready. Close/reopen
normally to check grid memory. This is one integrated rehearsal, not five checkpoints.

## Release direction and external inputs

The preceding map snapshot confirms e50bf5f364eb93965f9ecc0eb3ebfa80f86bf1ca, its four-path
commit and clean tree. No local terminal test summary accompanied that snapshot;
source review is complete, but local results are not inferred from a commit.

After local integrated acceptance, stop adding fake-only layers. The next larger task
is native candidate composition/preflight: bind existing approved profiles to both
boundaries, resource-specific service selection, clear disabled-state diagnostics and
one candidate regression pass. Keep execution disabled until actual approved inputs
exist. If those inputs are missing, list exact missing fields rather than fabricate
a profile or another simulated milestone. Connected-device acceptance and an authorized
release build remain later gates, not work performed here.

Historical source linkage is unchanged: 801-test evidence at 235f70ca..., wheel/staging
at 6074fdad..., startup-policy validation at 607c7db.... No hardware, second registry,
packaging, ID900 parsing or anneal changes were made.
