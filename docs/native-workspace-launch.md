# Native workspace launch, execution disabled

## Current launch modes, 2026-11-23

The disabled launch documented below remains the default. Two explicit modes exist:
`--simulate` (native-free whole-workspace simulation) and `--hardware-spectrum`
(real HORIBA Spectrum/Alignment only, no connection until operator action). The
flags cannot be combined. Native map, Annealing and laser execution remain disabled
in the latter mode. See [unified alignment](unified-alignment.md) for exact commands.
The older "no executable route" statements below describe the default candidate,
not the new explicitly selected HORIBA-only route.


Current operator tabs and draft validation: see [Native operator workflows](native-operator-workflows.md).
This launch-only checkpoint below is retained as historical context; the current window
reuses the existing map/spectrum panels while all hardware actions remain gated.

Base: 892b4cf7fba29b0fe925d72ee7b26016fadebfba, the fourteen-path working-lab
configuration migration commit. The supplied snapshot records a clean index/tree
and stable HEAD. The user reports local lint passed. No current local pytest,
preflight output or integrated Qt acceptance record accompanied that snapshot.
Historical validation remains tied to its original source revisions, not this HEAD.

## Launch

```powershell
uv run --no-sync labtools workspace launch examples/workspace/working-lab/candidate.json --headless
uv run --no-sync labtools workspace launch examples/workspace/working-lab/candidate.json
```

Headless launch composes the native candidate, prints configuration/selection/gate
status and closes the existing reservation session. It does not import Qt. Normal
launch opens a read-only native window with refresh and close controls. Connect,
map, spectrum and dark buttons are disabled. Refresh rechecks source hashes, not
devices; changed/missing files invalidate the displayed status. Close and relaunch
after editing source configuration. No simulation panels or synthetic data are used.
A missing Qt runtime is a launch failure, not a simulation fallback.

## Composition and execution gate

NativeWorkspace uses the existing WorkspaceOwnership/InstrumentSession authority,
DisabledNativeCandidate, WorkspaceMapTransport, WorkspaceSpectrumTransport and
SpectrumService. The ownership class lives under simulation for historical reasons;
its existing reservation-only implementation is reused, not copied or registered
again. No device handle is created on its executor. Existing map-worker and spectrum
coroutine affinity and operation-scoped cleanup remain unchanged.

The trusted constructor adapters target the existing LabJackU6, IDQTimeController,
ScanningMirror, SPADGate and HoribaSpectrometer wrappers. Every constructor first
hits an unconditional code-level refusal, before even importing its native module.
Public map/spectrum/dark requests also refuse. There is no --execute, --enable,
--discover, environment override, acknowledgement checkbox or manifest factory name.
These gates are engineering constraints, not a security sandbox against edited Python.
Future native enablement requires separately authorized implementation and acceptance.
No hardware discovery, SDK probe, network connection or hardware operation is run.

This batch provides the native launch/composition route, not executable acquisition
panels. It intentionally does not wire the existing simulation-oriented operator
panels into a native context or silently relabel their defaults as native settings.

## Explicit device-selection status

The launch report includes configured map and spectrum settings, source hashes,
both detector presets in the binding plan, and the active spectrum preset selection.
- LabJack: u6.U6(), implicit first-device selection; physical serial remains null.
- Counter: configured address/port, explicitly labelled not contacted.
- Detector: source expected index/type/dimensions/serial, grating, exit and ROI;
  these are expectations, never presented as readbacks or confirmed selection.
- Monochromator: first-discovered policy; physical identity remains null.
- Optical path: shared logical exclusion, not proof of physical shutter state.

Implicit selection is now visible and cannot accidentally execute through this route.
This does not pretend to implement serial-selecting LabJack or monochromator wrappers.
Those concrete connected-device selection/acceptance gaps remain before enablement.
Saved QSettings, installed ICL/calibration/runtime and shared-shutter state are still
runtime inputs, not a request for additional approval documents or invented values.

The working-source record and all migrated configuration files are unchanged. Anneal
stays at the user-authorized default software envelope -10/+10 V, respecting explicit
local profile limits. No anneal logic, ID900 parsing, packaging or registry changes.

## Validate locally

```powershell
uv run --no-sync ruff check --fix src/labtools/cli.py src/labtools/runtime/native_workspace.py src/labtools/gui/native_workspace.py tests/test_native_workspace_launch.py tests/test_native_workspace_window.py
uv run --no-sync pytest -q -ra tests/test_native_workspace_launch.py tests/test_native_workspace_window.py tests/test_source_candidate.py tests/test_native_candidate.py tests/test_workspace_map_transport.py tests/test_workspace_spectrum_transport.py
```

The actual Qt test creates/shows the window, checks disabled controls, refreshes
source status, invalidates a source and checks close cleanup. A missing Qt runtime
is an explicit skip and is NOT GUI acceptance. This smoke test is not a replacement
for the earlier integrated map/spectrum operator rehearsal. No earlier milestone is
closed from a commit, a skipped test or this disabled window alone.

The delivered validation record contains actual sandbox outcomes. New headless tests
forbid native/GUI imports, verify one authority, all constructor/public refusal paths,
source-change refusal, cancellation before coroutine start, repeated new-loop refusal,
cleanup on failed binding/GUI launch/context entry, and reopen recovery. Existing
fake-transport tests retain cancellation/cleanup/recovery and affinity coverage.
No full-suite, packaging or connected-device acceptance is claimed.

Next bounded work: record local results and actual window acceptance, then implement
one coherent native operator-workflow binding batch behind the existing gate. Resolve
physical-selection requirements before any authorized enablement; do not add another
fake-only milestone, registry, profile-search exercise or approval checklist.
