# Current architecture

This document describes the audited 28 October 2026 source, based on snapshot HEAD
`d2e29eb929567cdcc10bdf3fff907044c6815369`. Actual Git status is authoritative.
See [handover](ai-handover.md), [roadmap](refactor-roadmap.md) and
[audit](comparative-audit.md) for evidence and limitations.

## Package boundaries

- `cli.py` / `launchers.py`: lazy standalone dispatch, not a shared launcher.
- `config/`: validated requests, profiles and recipes; native-free HORIBA option tokens.
- `devices/`: physical wrappers; native imports remain inside real composition where possible.
- `runtime/`: session ownership, narrow services, providers and spectrum loop worker.
- `acquisition/`: measurement orchestration, cancellation, records and map checkpointing.
- `processing/`: Qt/native-free numerical transforms and legacy dark arrays.
- `io/`: pickle-free versioned spectrum/dark NPZ persistence. Keep this package.
- `simulation/`: explicit deterministic toy backends, not calibrated instrument models.
- `gui/`: Qt controls/controllers, settings snapshots and plotting of returned data.
- `visualisation/`: plotting and colour transforms.

Map persistence still lives in `acquisition/intensity_map.py`. Extracting it to `io/`
is deferred until a separate schema-/resume-compatible checkpoint, not mixed into this audit.
Compatibility exports remain in `operator_cli`, `gui.background`, `config.recipe_ui`
and `simulation.map_backend`; external users have not been inventoried for removal.

## Shared synchronous ownership

`InstrumentSession` is the process-local reservation authority for registered physical
resources. Mirror and gate alias one `labjack`. Factories, commands and close execute
on its worker. Whole-map reservations include checkpoint/home/gate cleanup. Faulted
normal commands are rejected; reviewed argument-free cleanup remains allowlisted.
Status snapshots are detached diagnostics, not authorization. Release does not close.
Shutdown refuses active leases and attempts all opened resource closes independently.
Zero-voltage home is movement, not a certified safe state. Native calls can block.

`SharedMirrorMapApplication` injects `ManualMirrorService` and `SharedMapProvider`.
Manual connect reserves without motion; disconnect releases only the lease. Shared
mode omits uncoordinated ITC laser control. Standalone tools do not join this session.

Real composition registers one fixed `time-controller:<canonical-IPv4>` count service
alongside LabJack. Maps reserve both atomically. IDQ construction/connect/configure/
count/disconnect stay on the session worker. Partial connect failure attempts cleanup
and retains its original error. The shared address policy is intentionally narrower
than general socket hostname resolution: no DNS alias equivalence is claimed. Multiple
addresses are possible in the session foundation, but this application exposes one
fixed controller, not dynamic multi-controller discovery. DLT/histogram/stream ownership
is not migrated. The legacy wrapper may swallow some disconnect errors internally.

Simulation composition owns one synthetic mirror/gate state; counters remain per-map.
Failure-injection measurement count resets per map. Position/gate ownership persists.
`gaussian-scene-v1`, coordinate/channel seeding, schema 1 and resume signatures remain
unchanged. Real failures never select simulation. Diagnostic snapshots are not hardware
readbacks and do not certify calibration, timing or interlocks.

## Spectrum service, records and loop ownership

`SpectrumService` is canonical orchestration for range and single-centre alignment.
Range operations produce immutable `SpectrumResult`/`DarkRecord` with configuration
identity. NPZ is authoritative; CSV/PNG are derivatives. Legacy CSV cannot acquire
provenance by attaching current settings. Fresh-dark range results may have no raw
array; alignment explicitly retains both raw and corrected arrays in `AlignmentResult`.
Alignment is a separate single-centre result contract, not a range SpectrumResult.

`SpectrumWorker` is an explicit job executor, not a second general device registry.
It owns one lazy thread/asyncio loop and rejects concurrent complete jobs. States are
unopened, starting, available, busy, faulted, closing and closed. It does not own a
persistent HORIBA connection: each service job still connects/configures/operates/
disconnects on that loop. Separate worker instances are not mutually exclusive; only
clients injected with the same worker coordinate. There is no cross-process exclusion.

Request/backend mismatch is rejected before worker startup. Startup failure is
published to callers; close/start races are serialized and self-join is rejected.
Shutdown refuses an active job, then drains tasks/async generators/default executor,
closes the loop and joins the thread. A blocked SDK/default-executor call can still
block shutdown. No forced interrupt or bounded deadline is claimed.

Cancellation is cooperative before opening and after a complete backend operation,
not per-frame or inside native calls. Busy ownership lasts through context cleanup.
Real operation failure faults the worker. Cancellation with failed real disconnect
also faults it while retaining CancelledError and cleanup notes. Teardown/reconstruction
is required; no automatic reconnect or synthetic fallback exists.

## GUI ownership and alignment

The ordinary spectrum GUI retains its existing operation-scoped AsyncTaskRunner and
standalone lifecycle; it does not automatically share SpectrumWorker with alignment.
Alignment snapshots settings on the UI thread and submits sequential jobs through the
worker. A Qt timer polls job completion; no raw vendor/loop object enters GUI code.
Injected workers survive tool close; private standalone workers close after active
cleanup. Busy is recoverable; real faults require application teardown. Stop/close
waits for the job boundary. Alignment repeats full connect/disconnect jobs, so no
high-rate persistent-connection performance is promised.

Native-free `config.horiba_presets` supplies the same gain/speed/default tokens to the
wrapper and alignment controls. Syncerity minimum is 0.065 s; Symphony minimum is
0.1 s. Alignment validation and both adapters enforce backend selection and exposure
floors without a 0.02 s override. No slit/ROI/grating commands were changed by this audit.

## Evidence and outstanding work

Offline fakes test orchestration, not SDK behaviour. QtWidgets tests are present but
were skipped in the audit environment. Physical LabJack, IDQ, HORIBA, shutter timing,
voltage calibration and optical safety remain unvalidated. Shared launcher integration,
wrapper failure reviews, operator-profile generalization and additional simulation
remain planned. Do not merge solely because headless tests pass.

## Alignment lifecycle hardening checkpoint

The window retains the job handle after Stop until polling observes completion. Start
is guarded against active handles, pending close and accepted close, not only the
repeat flag or disabled button. A faulted/closing/closed worker disables Start. Private
worker shutdown is owned by closeEvent alone; injected workers remain external. The
window timer stops on accepted close. New blocked-backend and QtWidgets acceptance
tests cover cleanup-delayed cancellation, busy conflicts, six failure stages and
private/injected close. Headless and QtCore tests passed; QtWidgets execution remains
blocked by missing libGL.so.1 here. See [acceptance](alignment-lifecycle-acceptance.md).

## Proposed lab-PC deployment boundary

The [deployment runbook](lab-pc-deployment.md) separates a protected non-editable
release environment from writable operator recipes/data and the maintainer-controlled
ProgramData profile. Side-by-side environments and protected launcher selection are
recommended; no auto-updater, account provisioning or ACL mutation is implemented.
Filesystem protection of the official installation is not a hardware security boundary
against arbitrary Python or administrators. No runtime source changed in this checkpoint.

## Device-wrapper audit boundary

The [wrapper audit](device-wrapper-audit.md) documents code-level failure gaps below
service adapters. In particular, real HORIBA disconnect can suppress a CCD close error
and skip monochromator close; a fake spectrometer that raises on disconnect does not
prove the real wrapper exposes that failure. IDQ also suppresses some teardown errors.
Existing worker/session fault contracts therefore cannot guarantee visibility of every
native cleanup failure until wrapper repairs land. No such repair is implemented here.

[Planned repairs](device-wrapper-repair-plan.md) preserve public facades and ownership:
InstrumentSession for registered synchronous services, owning asyncio loop for HORIBA,
borrowed LabJack for mirror/gate, and explicit DLT process/stream owners. No new general
resource manager or universal close semantics are introduced. Acquisition gate remains
open; no map allocation or physical command changes are made by this checkpoint.

## W1 ITC4000 lifecycle checkpoint (current)

Input snapshot: `labtools_source_20261029_075745.txt`, HEAD
`ad2a95b9813bc8407d54120a3997571c24d52450`, branch
`feature/shared-instrument-session`, upstream +1/-0. Recorded tracked worktree/index
clean; four earlier installers are untracked and preserved. Live Git remains authoritative.

W1 is IMPLEMENTED and OFFLINE-VALIDATED, not physically accepted. Startup cleanup now
covers manager creation, resource open, termination setup and *CLS. Both close stages
are attempted independently. Ordinary close failures raise ExceptionGroup retaining
all errors. KeyboardInterrupt/CancelledError remain primary, with other failures
attached structurally in _itc4000_cleanup_failures and human-readable notes. Startup
and context-body exceptions remain primary if cleanup also fails.

Once teardown starts, all command/query paths refuse use. Successful handles are
cleared; failed handles remain uncertain and _closed stays false. Only an explicit
close retries failed stages; successful stages are not repeated. Manager close may
invalidate an instrument whose close failed: retained handles do not imply a usable
session or guaranteed recovery. A failed constructor returns no wrapper; its original
exception/traceback and cleanup details remain the evidence for maintainer teardown.
No reconnect, command retry, destructor, laser-off, TEC-off or current-reset was added.

Constructor/public imports, defaults, units, SCPI strings/order, *OPC?/error/readback,
TEC policy and timeouts are preserved. Existing command/setter method ASTs are unchanged.
Finite-input policy (including the audited NaN constructor gap) remains W1b, not fixed.
IDQ get_histogram eval(raw) remains P0 and unfixed; fixture-backed parser hardening is
separate. No other wrapper, map allocation, schema/resume/model, profile or launcher
changed. Syncerity 0.065 s and Symphony 0.1 s remain unchanged.

Validation: 44 whole-module fake-PyVISA cases pass; focused ITC/service/import selection
179 passed; full offline suite 362 passed / 4 skipped, 172 inherited warnings. Baseline
rerun 318 passed / 4 skipped. QtWidgets still cannot load libGL.so.1. Changed-file Ruff
format/check, compileall, CLI/native-free smoke, TOML and wheel build passed. See
[itc lifecycle checkpoint](itc4000-lifecycle-checkpoint.md) for exact evidence, inventory,
installer/rollback/commit commands and remaining Windows/physical acceptance.

## W2 HORIBA lifecycle checkpoint (current)

Input snapshot: `labtools_source_20261029_084624.txt`, created
2026-10-29T08:46:24.4544246Z, HEAD `8293c1677d43e94fc9b50ede778cc5853dca5db7`,
branch `feature/shared-instrument-session`, upstream +2/-0. Tracked index/worktree
recorded clean; five earlier installers are untracked and preserved. Live Git is authoritative.

W2 is IMPLEMENTED and OFFLINE-VALIDATED, not physically accepted. Manager construction/
start, monochromator/CCD open, configuration and detector identity now share one startup
cleanup boundary. Disconnect attempts CCD close, the established one-second mono wait+
close, and manager stop independently. Ordinary cleanup failures are visible as
ExceptionGroup; cancellation/interrupt remains primary, with other cleanup failures in
_horiba_cleanup_failures and notes. Backend contexts now also preserve operation/cancellation
when disconnect raises BaseException and mark cleanup failure for real-worker faulting.

Teardown permanently refuses reconnect. Public mono/CCD/manager references are cleared;
failed handles remain private uncertain handles for explicit disconnect-only retry.
Successful stages are not repeated. Retained handles do not imply usability, especially
if manager stop succeeded. Successful disconnect is idempotent. No persistent connection,
automatic reconnect, command retry or timeout policy was added.

Preserved: public API/imports, detector identity/presets, optical tokens/units/readbacks,
command order, CCD/mono wait loops, one-second mono-close delay, capture/dark/reduction,
exposure setter/cache policy and 0.065/0.1 s minima. No 0.02 s override. ITC W1b, IDQ
P0 eval parser and all other wrappers remain separate; no map/launcher/profile/schema change.

Validation: 39 whole-module fake-SDK/backend/worker tests pass; focused selection
135 passed; full offline suite 393 passed / 5 skipped, 172 warnings. This environment
had no PyQt6, so QtCore plus four QtWidgets modules skipped; acquisition remains gated.
Changed-file Ruff, compileall, CLI/native-free smoke, TOML and wheel build passed.
See [W2 checkpoint](horiba-lifecycle-checkpoint.md) for exact inventory, limitations,
installer/rollback/commit commands and physical acceptance.
## W5 scanning-mirror preflight status

W5 is implemented/offline-tested at input HEAD `d2e29eb929567cdcc10bdf3fff907044c6815369`.
Both finite requests and representable calibrated codes are checked before either write;
A/B protocol and calibration maths remain unchanged. Channel-B ordinary failure now
reports uncertain partial movement with no rollback/home. Validation: 11 dedicated,
89 focused, full 404 passed / 5 skipped. PyQt6 is absent, so Qt remains gated. See
[W5 checkpoint](scanning-mirror-preflight-checkpoint.md). IDQ P0 remains open.
## UC480 lifecycle status

UC480 partial setup/start cleanup is implemented/offline-tested at HEAD `b4be98c4f619526a421af54f795365f14d95ac54`. Validation: 16 dedicated; 27 camera+regression; full 420 passed / 5 skipped. PyQt6 absent, so Qt remains gated. See [UC480 checkpoint](uc480-lifecycle-checkpoint.md). IDQ P0 remains open.

## SC10 checkpoint status

SC10 serial startup/teardown and fake transcript coverage are implemented at HEAD `f054ad5`. Full-suite validation must be rerun locally because the execution wrapper interrupted the combined run. See [SC10 checkpoint](sc10-lifecycle-checkpoint.md). IDQ P0 and Qt remain open.

## Scriptable measurement API requirement

The final product must provide a stable Qt-free `labtools.measurements` facade over shared services/acquisition logic, with validated immutable requests/results, explicit backend/profile provenance, session reservations, deterministic cleanup, progress/cancellation and GUI/script parity. Spectrum and intensity map delegate to existing services; hyperspectral must be rebuilt from the legacy runner before export. See [scriptable measurements](scripted-measurements.md).

Kinesis finite native-unit validation and close ownership are implemented at HEAD `bea41a66`; 15 dedicated fake-SDK tests passed. Full-suite rerun remains local because the execution wrapper interrupted it. See [Kinesis checkpoint](kinesis-lifecycle-checkpoint.md).

## Scripted spectrum facade

The Qt-free spectrum facade is implemented; see [checkpoint](measurements-spectrum-checkpoint.md) and [usage](scripted-measurements.md). Map, hyperspectral and anneal facades remain planned.

## Scripted dark records

Qt-free dark capture, immutable reuse and NPZ helpers are implemented; see [checkpoint](measurements-dark-checkpoint.md).

## Scripted alignment frames

Qt-free sync/async alignment acquisition is implemented; see [checkpoint](measurements-alignment-checkpoint.md).

## Scripted intensity maps

The Qt-free resumable intensity-map facade is implemented; see [checkpoint](measurements-intensity-map-checkpoint.md). Map algorithms, schema and persistence are unchanged.

## Unified measurement runtime

A Qt-free `MeasurementRuntime` now composes the existing spectrum and map runtimes without changing their ownership models; see [checkpoint](measurements-runtime-checkpoint.md).

## Versioned measurement recipes

Strict schema-version-1 JSON recipes now cover the implemented spectrum, dark, alignment and intensity-map facades; see [checkpoint](measurements-recipes-checkpoint.md) and [usage](scripted-measurements.md).

## Measurement recipe dispatch

A Qt-free single-recipe dispatcher now covers the four implemented schema-v1 recipe kinds and requires explicit confirmation before real execution; see [checkpoint](measurements-dispatch-checkpoint.md).

## Hyperspectral acquisition service boundary

`labtools.acquisition.hyperspectral` is an internal, Qt-free service boundary. It composes the existing `SpectrumService` with a whole-operation mirror context, preserves row-major legacy scan order, reports typed scientific-boundary progress, and writes atomic schema-version-1 NPZ datasets with explicit completion masks and synthetic provenance. It deliberately does not alter the public measurements package, recipe dispatcher, CLI, or GUI.

### Hyperspectral real-resource composition

The operation-scoped `HyperspectralMirrorProvider` leases the session `mirror` resource, including its LabJack, before any device opens and releases it only after context cleanup. HORIBA ownership remains within `SpectrumService`; the current session cannot truthfully reserve that separately. Failures surface as `HyperspectralAcquisitionError` with an immutable partial result and the original exception as cause.

### Persistent hyperspectral spectrum ownership

`SpectrumService.operation` is the narrow multi-acquisition contract: one exact `SpectrumSettings` value, one live range backend, normal SpectrumService validation/dark/result semantics, and outer-context teardown. `open_real_range` ties a process-local exclusive ownership lock to the actual HORIBA object's lifetime. `open_hyperspectral_service` acquires mirror ownership before spectrum ownership and lends both dependencies without transferring closure responsibility.

### Hyperspectral failure contract

Ordinary point acquisition failures are exposed as `HyperspectralAcquisitionError` with the immutable partial result and original exception as cause. Cancellation returns an immutable cancelled partial result. `KeyboardInterrupt` and `SystemExit` bypass ordinary failure wrapping. Ownership cleanup diagnostics attach to the primary error rather than replacing it.

Combined hyperspectral acquisition and persistence failures retain the acquisition error as cause and attach persistence diagnostics. Clean persistence failure remains directly visible. Mirror-context exit failure produces a failed immutable diagnostic result, even when all points were acquired, because resource cleanup did not complete successfully.
