# Native operator-workflow binding, execution still disabled

## Accepted starting checkpoint

labtools_evidence_20261119T123312Z.txt records 190c1a0e4d66ad58c55b3be7aacf6ce66250bbd2,
the eight-path native launch commit and clean tree/index before/after validation.
Local ruff check --fix passed; the captured focused run passed 101 tests, no skips,
16 pydantic deprecation warnings in 10.52s. Headless launch exited 0 with execution
disabled and no hardware/environment access. The user confirms the window opened;
the actual native-window Qt test passed in that local run. This closes that launch
checkpoint only. It does NOT establish the earlier integrated acquisition rehearsal
or connected-device acceptance. Historical validation remains linked to its revisions.

## What changes

The existing native launch window now contains Configuration/draft preview, Intensity
map and Spectrum tabs. The latter reuse the actual existing IntensityMapWindow,
HoribaRangeWindow, MapController/MapWorker, AsyncTaskRunner/SpectrumService and owned
workspace adapters. No second acquisition implementation, device registry, executor
or fake scene is added. Existing simulation/standalone defaults remain unchanged.

```powershell
uv run --no-sync labtools workspace launch examples/workspace/working-lab/candidate.json
```

Both panels start from the migrated native source recipe, not the old standalone
QSettings or toy defaults. Map hidden pins/address/envelope remain source-bound.
Spectrum detector options come from the source profile; selecting Symphony previews
its expected serial/ROI/optics, not connected-device readbacks. Source selection
policies remain explicit: implicit u6.U6() and first-discovered monochromator, no
invented serials or device discovery. Laser state is NOT PROBED, not OFF/read back.

Change grid/integration or spectral settings, then use Validate and preview operator
drafts. The report separates immutable source status from the in-memory draft. It
validates settings and source hashes without creating outputs, opening hardware or
saving preferences. Detector expectations are detached copies, not mutable aliases
into the source plan. Address/pins/software limits require editing source/relaunch;
UI draft validation cannot expand them. Native draft preferences are intentionally
not read/written through standalone real/simulation QSettings. Closing discards drafts.
No approved physical wavelength/voltage limits are invented by preview validation.

The existing offline dark loader remains available when selected. Previewing pre-taken
subtraction requires a compatible dark record and reports its ID. Capture/connect/
acquire/resume and laser controls are disabled/refused; loading a file is not a device
operation. Native requests remain backend=real, never silently simulated or labelled
as synthetic. No acquisition outputs are created by this gated candidate.

## Gate and lifecycle

Public UI entry points refuse before creating workers or reserving resources. The
map worker injection is workspace.acquire_map; the spectrum service injection is
workspace.spectrum_service. Those validate drafts and source hashes, then hit the
existing DisabledNativeCandidate refusal. Native constructor gates still refuse
before imports. There is no enable flag, environment override or acknowledgement.

The existing owned adapters retain their reservation-until-idle/thread-finished
release paths. Their constructor parameters now allow native mode/options explicitly;
defaults preserve simulation callers. If a worker is invoked directly by a developer,
the runtime gate still refuses and the existing cleanup paths release leases. Close
requests while a worker is finishing request cancellation and wait for cleanup rather
than closing the session early. No native handle is retained or moved to the session
executor; operation-scoped map thread and spectrum coroutine affinity is preserved.
Source edits invalidate preview/refresh and require relaunch. No source/profile file,
working-lab capture, provenance record, anneal default or explicit local limit changes.

## One local validation pass

```powershell
uv run --no-sync ruff check --fix src/labtools/runtime/native_workspace.py src/labtools/runtime/native_workflows.py src/labtools/gui/native_workspace.py src/labtools/gui/native_workflow_panels.py src/labtools/gui/workspace_panels.py tests/test_native_workflow_binding.py tests/test_native_workflow_window.py
uv run --no-sync pytest -q -ra tests/test_native_workflow_binding.py tests/test_native_workflow_window.py tests/test_native_workspace_launch.py tests/test_native_workspace_window.py tests/test_source_candidate.py tests/test_native_candidate.py tests/test_workspace_config.py tests/test_workspace_ownership.py tests/test_workspace_map_transport.py tests/test_workspace_spectrum_transport.py
```

New headless tests forbid device/SDK/Qt imports, cover exact source defaults, valid
edits, invalid backend/identity/address/pins/envelope/options, no output/source writes,
worker-thread/new-loop refusal, cancellation/refusal recovery and closed-service use.
The actual Qt test checks source defaults in the real panels, draft preview, both
preset selection, disabled entry points, native-import refusal, actual MapController
and AsyncTaskRunner refusal/cleanup/reuse, no standalone preference changes and close.
The new Qt tests skip on a missing runtime, not acceptance. Sandbox Ruff passed.
The focused selection produced 152 passed, 2 skipped and one environment failure in
205.63s: the older workspace-ownership subprocess test found the installed PyQt6
package but could not load libGL.so.1. The two new/current native-window checks also
could not load that library and skipped. No actual Qt acceptance is claimed here.
PyQt6 installation in the sandbox did not supply the missing system graphics library;
no dependency change is requested on the user PC. The delivered record/log retains
the failure, rather than relabelling it as a pass or rerunning successful tests.

## Remaining release gates and next task

After local acceptance, close operator binding; do not add another gated/fake-only
milestone. Remaining native execution work requires separate explicit authorization.
One coherent enablement batch should address concrete device-selection policy and
native operation entry points, operator status/cancellation/cleanup, and one offline
candidate regression, followed by connected-device acceptance on the lab PC. Do not
infer that source expected detector serials or an implicit first-device policy are
physical readbacks. If enablement is not authorized, stop with these release gates
rather than implementing another layer of disabled controls.

The earlier integrated acquisition rehearsal remains open until actual evidence is
provided. Packaging/release deployment is not part of this batch. No hardware,
ID900 parsing, anneal changes or second registry. Historical 801-test evidence stays
at 235f70ca..., wheel/staging at 6074fdad..., startup-policy validation at 607c7db....
