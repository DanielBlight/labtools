# Development handover: HORIBA lifecycle W2 and open Qt gate

## Starting identity and evidence

Current input: `labtools_source_20261029_084624.txt`, created
2026-10-29T08:46:24.4544246Z, HEAD `d2e29eb929567cdcc10bdf3fff907044c6815369`,
branch `feature/shared-instrument-session`, upstream +2/-0. Tracked index/worktree
recorded clean. Five earlier installers are untracked and preserved. No complete local
Qt acceptance pass log is embedded. Actual live Git state is authoritative.

Current checkpoint implements HORIBA W2 only: two production lifecycle boundaries, one
whole-module fake SDK test module and relevant docs. No hardware/Git/account/deployment
action, dependency, profile or acquisition feature changed. Acquisition gate remains open.

Read [architecture](architecture.md), [audit](comparative-audit.md),
[roadmap](refactor-roadmap.md) and [conventions](development-conventions.md).
Historical batch notes are not current task lists.

## Implemented

- Lazy standalone CLI/launchers and compatibility exports.
- InstrumentSession reservations, aliases, lazy services, fault latching and reviewed cleanup.
- Shared manual mirror/map composition, shared synthetic mirror/gate state and fixed-address
  shared IDQ count service. Standalone paths remain independent.
- SpectrumService, immutable range/dark records, NPZ persistence and ordinary GUI migration.
- Dedicated spectrum asyncio-loop worker, but operation-scoped backend connections.
- Alignment service/worker client with fresh-dark subtraction and immutable raw/corrected data.
- Native-free detector option data shared by wrapper and alignment; minima 0.065/0.1 s.

Audit corrections: partial IDQ startup cleanup; alignment exposure/backend guards;
worker startup/close race and startup-error reporting; worker request/backend guard;
failed-disconnect cancellation faulting; native-free alignment construction; per-map
synthetic failure counter; clearer alignment submission/fault presentation.

## Ownership rules and compatibility

InstrumentSession remains the synchronous resource authority. Hold leases through all
cleanup. Tool close is not application shutdown. IDQ sockets belong to the session
worker. HORIBA objects belong to the job's asyncio loop; never cache them across
AsyncTaskRunner loops. Only clients sharing the same SpectrumWorker coordinate jobs.
Worker close refuses active jobs. Native calls are not forcibly interruptible.

Keep physical commands/units/pins/limits, QSettings, CLI/import paths, schema 1,
resume signatures, deterministic model and raw/dark provenance. No real failure may
fall back to simulation. No 0.02 s alignment override. Negative corrected values stay.
Keep `io/`; map persistence extraction is a separate future task.

## Alignment lifecycle checkpoint: implementation and evidence

The preceding lifecycle checkpoint added deterministic blocked-backend and Qt window regressions.
Start cannot replace a still-owned job after Stop, while closing, or after accepted
close. Faulted/closing/closed workers disable Start. Private-worker shutdown now has
one closeEvent owner rather than duplicate calls during deferred close. Injected
workers remain application-owned. The timer is stopped after accepted close.

New tests: seven native-/Qt-free blocked-backend cases, and twelve QtWidgets cases
covering stop/restart, external busy owner, cleanup-delayed close, six failure stages,
private/injected ownership, settings snapshot thread and plot/result identity.

Validation: focused backend/worker/audit/QtCore selection 32 passed. Full offline suite
318 passed, 4 skipped, 172 inherited Matplotlib/pyparsing warnings. Changed-file Ruff
format/check passed with Ruff 0.17.3. Compileall, CLI help, TOML parsing, wheel build and
relative Markdown target checks passed. Python 3.12.15, PyQt6 6.11.0 installed only in a
temporary validation directory, not a reproduced uv.lock/Windows environment.
QtCore tests now run (8 passed); QtWidgets cannot load because libGL.so.1 is missing.
Skipped modules: alignment GUI, ordinary spectrum GUI, GUI lifecycle and new alignment
window acceptance. Windows/QtWidgets and physical acceptance are NOT complete.
See [lifecycle acceptance](alignment-lifecycle-acceptance.md) for exact commands.

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = "offscreen"
$env:MPLBACKEND = "Agg"
uv run --no-sync python -m pytest tests/test_alignment_lifecycle_acceptance.py tests/test_alignment_window_acceptance.py tests/test_alignment_gui.py tests/test_spectrum_gui_phase1.py tests/test_gui_lifecycle.py tests/test_qt_controllers.py -q -rs
uv run --no-sync python -m pytest -q
uv run --no-sync python -m compileall -q src tests examples
uv run --no-sync python -m labtools --help
git diff --check
git status --short
```

Keep 0.065 s Syncerity and 0.1 s Symphony minima. No new backend, launcher, persistent
connection or device command was added. Remove QT_QPA_PLATFORM=offscreen before
interactive GUI checks. Do not treat a skipped module as acceptance.

## Physical validation still required

LabJack wiring/voltage calibration and gate timing; IDQ firmware/channel/timeout/socket
lifecycle; HORIBA preset discovery, shutter/dark correctness, exposure timing and SDK
loop teardown. Existing SC10/ITC/camera/stage and hazardous anneal/hyperspectral paths
are not certified by these tests. No physical endpoint was contacted.

## Next bounded task and separate work lanes

W2 HORIBA lifecycle is implemented/offline-tested; see
[W2 checkpoint](horiba-lifecycle-checkpoint.md). Next fixture-independent wrapper task
is W5 DAC/mirror two-axis preflight only: validate both finite inputs and representable
codes before either write, retain byte encoding and report second-write partial movement
without rollback/home. Do not combine with another wrapper. If representative accepted
IDQ histogram fixtures become available, prioritize isolated P0 parser hardening instead.

Acquisition lane remains separate: execute/fix QtWidgets gate, then collision-safe map
allocation. Current suite 393 passed / 5 skipped does not establish Qt or physical acceptance.
W1 ITC finite-input policy, HORIBA timeout/exposure policy and persistent connections remain planned.

## Git workflow

Installer targets the exact current snapshot, including any future intended dirty
state only if its affected bytes match. It does not stage/commit/merge/push/reset.
Review changed files and preserve unrelated changes. Keep backups outside the repo.
Do not merge until local Ruff/Qt acceptance and required physical review are recorded.

## Historical deployment-documentation checkpoint and gate rerun

See [lab-PC deployment](lab-pc-deployment.md) and [gate status](qt-gate-status.md).
The guide proposes non-editable wheel releases, protected code/profile/launchers,
standard operator accounts, writable recipes/data, offline bundles and side-by-side
updates/rollback. It is a maintainer runbook, not University IT policy or an executed
Windows installer. Windows commands/ACL examples require IT review and local acceptance.

Gate rerun: 15 passed, 4 skipped. QtCore/headless cases pass; all four QtWidgets modules
skip because libGL.so.1 is unavailable. Full offline suite: 318 passed, 4 skipped,
172 inherited warnings. Existing lifecycle Python Ruff check passed (0.17.3).
Do not implement collision allocation or launcher work until the QtWidgets cases
execute and pass, or supplied local output explicitly establishes that result.

Next task remains: run/fix the QtWidgets gate; then collision-safe map directory
allocation in one bounded checkpoint. Keep output schemas/resume/determinism and
0.065/0.1 s detector minima unchanged. No new runtime behaviour is claimed here.

## Historical wrapper-audit validation (pre-W1)

Qt gate rerun: 15 passed / 4 skipped. Full offline suite: 318 passed / 4 skipped,
172 inherited warnings. All four QtWidgets modules still skip (libGL.so.1 missing).
Eight extracted-method fake-handle probes confirm specific ITC/HORIBA/DAC/UC480 defects;
these are not whole-module or hardware tests. Device Ruff check passes and all 12 device
Python files are formatted. See the checkpoint for compile/build/import/link evidence.
No wrapper rewrite or collision fix is implemented by this documentation checkpoint.
Earlier counts and deployment statements above remain historical evidence where labelled.

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

## Latest checkpoint: internal hyperspectral service

A Qt-free internal hyperspectral configuration/service/result boundary now composes `SpectrumService` with an operation-scoped mirror factory. It has deterministic synthetic provenance, point-boundary cancellation, atomic pickle-free NPZ persistence, and no public measurement/recipe/CLI/GUI exposure. Resume and a reviewed real mirror/session adapter remain intentionally unimplemented.

### Hyperspectral hardening follow-up

The service now has an operation-scoped session mirror provider and a dedicated acquisition error carrying immutable partial data. Offline tests prove conflict-before-open and reservation lifetime. A unified enforceable HORIBA reservation is still absent and physical acceptance remains outstanding.

### HORIBA operation ownership resolved in-process

Hyperspectral composition now uses `SpectrumService.operation` to keep one configured backend for a full cube. Real range creation is process-locally exclusive and conflict rejection occurs before native construction. This is not a cross-process lock and is not physical acceptance.

### Hyperspectral failure matrix completed offline

The focused matrix now exercises point failures, axis drift, partial cancellation, immutable partial results, close ownership and primary preservation. Existing HORIBA lifecycle tests provide startup/disconnect cleanup evidence. No physical or Qt acceptance is implied.

The final offline hyperspectral matrix adds startup/exit, combined persistence, `SystemExit`, and runtime import-isolation cases. Public hyperspectral APIs remain intentionally absent.

### Public hyperspectral facade checkpoint

Hyperspectral is now additively exposed for scripted measurement, strict version-1 recipes and guarded single-recipe dispatch. GUI integration, resume, pipelines and anneal remain unsupported. Real confirmation is intent-only and does not establish laser, shutter, optical-path, sample or hardware safety.

The public hyperspectral contract is hardened: exact additive exports are tested, existing output paths reject before runtime creation, borrowed ownership is preserved, cleanup handles multiple failures, and cancelled partial results survive operation-context exit.

### Simulation-first hyperspectral GUI

A minimal Qt window/controller now consumes the frozen public facade, exposes unit-bearing simulation inputs, progress, cancellation and synthetic result summaries. It has no real-mode control, resume, laser/shutter policy or physical acceptance.

The hyperspectral GUI hardening adds selected-pixel spectra, completed-mask validation, pre-taken dark loading, formal operator states, cleanup-wait close handling, and a lazy source-checkout launcher. It remains simulation-only.
