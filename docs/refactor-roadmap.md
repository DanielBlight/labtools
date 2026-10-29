# Refactor roadmap: audited status

Based on input snapshot HEAD `d2e29eb929567cdcc10bdf3fff907044c6815369`.
See [audit](comparative-audit.md) and [handover](ai-handover.md). Offline validation is
not hardware acceptance. Existing wrapper matrix below remains the review backlog.

## Completed foundations and status

| Phase | Actual state | Remaining acceptance |
|---|---|---|
| Structural cleanup and processing | Implemented; offline tested | Standalone Windows/driver acceptance |
| 1: spectrum service and ordinary GUI | Implemented; headless tests pass | Qt lifecycle/export tests skipped here |
| 2: shared manual/map composition | Implemented opt-in, not a launcher | Qt/physical LabJack validation |
| 3a: shared simulation | Implemented; deterministic/resume tests pass | Qt interaction acceptance; not a physical model |
| 3b: IDQ count ownership | Implemented for one fixed canonical IPv4 in shared app | Physical socket/firmware validation; not DNS/multi-controller discovery |
| 4a: spectrum loop worker | Implemented persistent loop only | No persistent connection; race fixes tested, SDK/Qt validation outstanding |
| 4b: alignment client | Implemented with separate immutable single-centre result | Partial acceptance: Qt/fault/close coverage and physical shutter timing outstanding |

The audit corrected exposure/backend guards, native-free options, IDQ partial startup,
worker startup/close races and cancellation-cleanup faulting. It did not implement a
shared launcher, DLT/histogram ownership or persistent HORIBA connections.

## Alignment lifecycle acceptance checkpoint

Status: IMPLEMENTED AND PARTIALLY VALIDATED. Blocked-backend tests pass; QtCore tests
run. QtWidgets/Windows acceptance remains BLOCKED in the implementation environment
by missing libGL.so.1. The twelve new window cases must execute locally, not skip.

The window rejects start while an old job/close remains owned, disables Start after
worker fault/close, and shuts a private worker from closeEvent only. Stop remains
cooperative; ownership lasts through backend cleanup. Injected workers survive close.
Validation: 318 passed, 4 skipped; changed-file Ruff passes. See
[lifecycle acceptance](alignment-lifecycle-acceptance.md). No hardware was contacted.

## Next bounded implementation after the local Qt gate

Collision-safe map output directories: preserve the legacy first timestamp directory,
allocate a distinct directory on collision, never overwrite data, and test immediate
retry plus concurrent allocation. Keep schemas/resume/model unchanged. Do not bundle
launcher work or map persistence extraction into this reliability fix.

Phase 7 remains the shared launcher phase. Phase 5 remains wrapper reliability. Neither
is declared complete by these tests. Persistent HORIBA connections remain unimplemented.

## Phase 5: wrapper reliability and hazardous-workflow review

Status: PARTIAL implementation; wrapper audit and repair plan COMPLETE as documentation, not runtime remediation. LabJack startup and existing camera cleanup work remain; other findings are not fixed. Prerequisite: each wrapper's consumer
inventory; independent bounded tasks, not a sweep. Model: capable coding model for
small lifecycle adapters; strong reasoning plus hardware owner for hazardous policy.
Files: devices/*, acquisition/laser_anneal.py, run_hyperspectral_scan.py, relevant GUIs.

Follow matrix below. Start with transport cleanup and explicit error reporting.
Review HORIBA start failure/disconnect independence, ITC constructor resource leak,
SC10 close-vs-shutter semantics, UC480 partial live startup and IDQ/DLT teardown.
Replace IDQ histogram eval only after representative response fixtures establish
accepted grammar; no guessed SCPI changes. Review anneal shutter/stage/mirror
failure cleanup and misleading status separately. Legacy hyperspectral code is
not approved for unattended operation: laser-off dark is not explicitly enforced
and exception cleanup is incomplete. Do not run it as a test.
Tests: injected failure at each startup/close stage, primary error preservation,
no unexpected commands; then opt-in hardware acceptance for each affected device.
Acceptance: each commit documents changed failure behavior and preserved success
sequence. Hardware REQUIRED for release. Risk: changing emission/shutter state or
masking original errors. Checkpoint: one wrapper or workflow per reviewed commit.

## Phase 6: operator profiles and recipes across tools

Status: annealing IMPLEMENTED; generalization PLANNED. Prerequisites: service seams
from Phases 1-4. Model: capable coding model, maintainer/operator review.
Files: config/, examples/profiles/, recipe controls, service composition.
Extend strict JSON schemas using existing recipe/profile separation. Add spectrum
configuration_id to maintainer context; no invented calibration values. Add map
recipes without changing checkpoint signatures. Preferences stay per-user; backend
selection is explicit and locked during jobs. Test unknown fields, bool/numeric
validation, protected limits, missing profile, load/save without device access and
metadata provenance. Acceptance: operators edit recipes, not Python; no automatic
output enabling or safety-ack restoration. Hardware not required for schema tests;
REQUIRES OPERATOR-WORKFLOW VALIDATION and maintainer-approved hardware profiles.
Risk: weakening limits or treating approved as safety proof.
Checkpoint: one workflow's recipe/profile integration per commit.

## Phase 7: shared launcher and remaining tool migration

Status: PLANNED. Prerequisites: Phases 2-4 and reviewed hazardous workflows before
exposing them in shared mode. Model: strong reasoning for composition; capable
coding model for panels and lazy registration.
Files: future application root/tool registry, launchers.py, cli.py, gui controllers.
Build one QApplication/main window; registry entries construct windows/panels from
injected services, not drivers. Keep standalone commands as composition adapters.
Show real/synthetic/profile/availability/busy/fault states; separate tool close from
app shutdown. Migrate camera/anneal/other tools incrementally; do not offer concurrent
use until all shared physical resources are represented. Tests: lazy registry,
multiple windows, conflict, independent tool close, shutdown during job/failure,
no native imports for help/simulation. Acceptance: no competing driver creation,
existing launch paths work. Hardware acceptance per migrated tool REQUIRED.
Risk: false shared-ownership claim and accidental source enabling.
Checkpoint: launcher skeleton, then one tool per commit.

## Phase 8: expanded simulation, compatibility retirement and release

Status: PLANNED. Prerequisites: stable consumer contracts and earlier acceptance.
Model: capable coding model for simulations/docs; strong review for removals.
Files: simulation/, contract tests, compatibility shims, docs/commands.md, packaging.
Add camera/stage/shutter/laser simulations only for consumed workflows, with explicit
state models/provenance. Do not model hazardous safety success as hardware proof.
Search imports/scripts/entry points and confirm external operator consumers before
removing old operator_cli, gui.background, config.recipe_ui, simulation.map_backend
or range_spectrum exports. Migrate useful historical docs before deleting anything.
Tests: shared contract tests, full offline/Qt suite, build/install/import smoke,
doc links, actual locked Windows environment and reviewed hardware checklist.
Acceptance: release evidence separates synthetic, fake SDK, Qt, driver and physical
checks; no obsolete API removed without migration note. Hardware REQUIRED for
release, not synthetic tests. Risk: breaking external scripts and environment setup.
Checkpoint: each compatibility removal separate from release/validation records.

## Device/wrapper migration matrix

All real wrappers require hardware validation before release. Classification is
work scope, not a claim that every wrapper is broken. No REPLACE classification
is justified by the inspected snapshot. External consumers remain OPEN.

### HORIBA, devices/horiba_spectrometer.py
**ADAPT TO NEW CONTRACT; REQUIRES HARDWARE VALIDATION**, Phases 1/4/5.
Role: async mono+CCD, presets/configuration, capture/reduction. Consumers: spectrum
GUI, range_spectrum (type contract), legacy hyperspectral runner, scripts/horiba/*,
new runtime/spectrum_backend. Lifecycle: inert constructor, async connect/disconnect,
async context. Simulation: new range-service toy adapter, NOT SDK simulation.
Issues: manager.start outside connect cleanup try; disconnect can skip mono after
CCD close error and suppress errors; no new polling deadlines; get_spectrum mean
zero-frame validation gap; configure exposure minima vs direct setter behavior.
Work: reviewed cleanup/state/affinity adapter, not new commands. Compatibility:
retain get_spectrum/get_dark_spectrum, preset identity/configuration and old exports.
Tests: fake SDK lifecycle/partial startup/close, range adapter, real shutter/TTL,
calibration and detector selection. Hardware diagnostics docs mention acquire_frame
and _wait_for_mono arguments absent in this wrapper: INVESTIGATE FIRST, do not run
those scripts unchanged or invent missing semantics.

### LabJack U6, devices/labjack_u6.py
**MINOR CLEANUP; REQUIRES HARDWARE VALIDATION**, Phases 2/5.
Role: owned U6 transport. Consumers: map_devices, mirror_backend, labjack_service,
annealing, legacy hyperspectral; borrowed mirror/gate wrappers.
Lifecycle: eager open/calibrate/delay; context closes. Simulation: map synthetic
capabilities, no emulated U6 transport. This batch fixes cleanup after a returned
handle's calibration failure and successful close idempotence. Constructor failures
inside u6.U6 before return remain vendor-owned. Work: retain API; add service/profile
identity only when needed. Tests: new lifecycle fake module plus session/backend
regressions; real calibration/reconnect. No voltage/digital commands changed.

### Scanning mirror / _LJTickDAC, devices/scanning_mirror.py
**KEEP; ADAPT TO NEW CONTRACT at service boundary**, Phases 2/5.
Role: calibrated I2C DAC movement, zero-voltage home. Consumers: mirror_backend,
map_devices, labjack_service, annealing, legacy hyperspectral. Lifecycle: borrowed
U6; constructor reads DAC calibration, no owned disconnect. Simulation: map mirror.
Issues: raw wrapper has no bounds; callers/services enforce differing approved
limits. Work: preserve DAC bytes/calibration and home target; central profile checks
without silently widening limits. Tests: fake I2C/calibration/partial writes, service
bounds/conflicts; hardware voltage/readback/wiring validation. No cosmetic rewrite.

### SPAD gate, devices/spad_gate.py
**KEEP; ADAPT TO NEW CONTRACT at service boundary**, Phases 2/3.
Role: borrowed U6 digital high/low gate. Consumers: map_devices, labjack_service.
Lifecycle: no owned connection; close is output-low, not resource release.
Simulation: map gate. Work: preserve pin/polarity, alias to LabJack; explicit cleanup
failure reporting. Tests: fake digital writes, conflict/cleanup, real gate timing and
polarity. Compatibility: never reinterpret close() as disconnect or auto-home.

### IDQ controller, devices/idq_time_controller/controller.py
**INVESTIGATE FIRST; ADAPT TO NEW CONTRACT; REQUIRES HARDWARE VALIDATION**, Phases 3/5.
Role: SCPI/ZMQ counts, histograms, timestamps. Consumers: map_devices, shared_map
real_counter, IDQ/timestamp hardware tests. Lifecycle: explicit connect/disconnect,
context, DLT streams/processes. Simulation: map count capability only.
Issues: global REC state, ZMQ owner affinity, partial socket startup, broad teardown
suppression, eval(raw) in histogram parser. Work: count service first; streaming
migration separately, fixture-backed safe parser, deterministic independent cleanup.
Compatibility: package re-export IDQTimeController, units/SCPI/stream callbacks.
Tests: fake sockets/response fixtures/failure teardown; hardware counts/histogram/
stream completion and DLT flush before claiming conformance.

### IDQ DLT, devices/idq_time_controller/dlt.py
**INVESTIGATE FIRST; SUBSTANTIAL REFACTOR if lifecycle evidence requires**, Phase 5.
Role: subprocess launch, ZMQ request helper and receiver threads. Consumers: IDQ
controller. Lifecycle: dlt_connect creates context/socket; StreamClient owns receive
context; subprocess ownership is split between helpers/controller. Simulation: none.
Issues: context/process ownership and join timeout; do not assume a stopped flag
means thread exit. Work: explicit owners and cleanup tests before extraction.
Compatibility: DEFAULT_DLT_PATH, helper APIs and timestamp dtype/units.
Tests: fake process/socket/thread, timeout/flush/partial start; Windows DLT REQUIRED.

### ITC4000, devices/itc4000.py
**MINOR CLEANUP then ADAPT TO NEW CONTRACT; REQUIRES HARDWARE VALIDATION**, Phases 5/7.
Role: laser diode/TEC VISA control. Consumers: spectrum GUI, intensity GUI via
runtime/lazy_devices, legacy hyperspectral. Lifecycle: eager ResourceManager/open/
*CLS, close releases VISA only; explicit disable controls emission.
Simulation: none; map simulation disables real laser controls.
Issues: partial constructor leak, GUI thread blocking, close is not diode-off,
shutdown status can conceal unknown output. Work: reviewed owner/service and startup
cleanup; do not alter thermal/output sequencing casually. Compatibility: address,
threshold/max current, enable/disable and TEC defaults. Tests: fake VISA command
order/error/partial startup, real interlocks/readbacks with approved optical setup.

### SC10, devices/sc10.py
**MINOR CLEANUP / ADAPT TO NEW CONTRACT; REQUIRES HARDWARE VALIDATION**, Phases 5/7.
Role: serial shutter controller. Consumers: anneal acquisition/GUI, hardware tests.
Lifecycle: explicit connect (optional auto_connect), identity verification, serial
close/cancel I/O. Simulation: none. Issues: cleanup failures can replace startup
error; serial release does not establish shutter state. Work: service-level reviewed
shutter policy, independent cleanup reporting; preserve toggle/readback semantics.
Tests: fake echo/timeout/close, existing opt-in modes, physical shutter/wiring.
Compatibility: enums, command grammar, set_enabled behavior, COM defaults.

### Kinesis rotation stage, devices/kinesis_rotation_stage.py
**MINOR CLEANUP; REQUIRES HARDWARE VALIDATION**, Phases 5/7.
Role: native-coordinate stage. Consumers: anneal acquisition/GUI. Lifecycle: inert
constructor, explicit connect/context, close, sole-device discovery.
Simulation: none. Issues: constructor failure before handle return, timeout/stop
semantics, stage-return failure can mask acquisition failure in caller. Work: test
lifecycle/cleanup and caller policy, preserve native units/discovery and no implicit
home. Tests: fake discovery/move/wait/close, real coordinate/readback/return behavior.

### UC480 camera, devices/uc480_camera.py
**MINOR CLEANUP then ADAPT TO NEW CONTRACT; REQUIRES HARDWARE VALIDATION**, Phases 5/7/8.
Role: camera snap/live. Consumers: anneal GUI, camera diagnostic.
Lifecycle: explicit connect, live start/stop, independent stop+close attempts.
Simulation: none. Issues: start_live can partially start before _live flag is set;
connection cleanup may mask primary error. Work: preserve frame ownership,
horizontal flip, BGR GUI interpretation and exposure units; inject camera service
before shared use. Tests: existing fake cleanup/frame tests plus partial live start,
settings changes/stop/close; Windows DLL and actual camera preview REQUIRED.

## Compatibility and unresolved validation register

- Keep IntensityMapConfig/SCHEMA_VERSION re-exports, range DarkSpectrum/subtraction
  exports, old launcher aliases, operator_cli/gui.background/config.recipe_ui/
  simulation.map_backend shims. No known consumer removed in this batch.
- OPEN: external scripts and operator workflows not included in snapshot.
- REQUIRES HARDWARE VALIDATION: all real adapters and changed LabJack failure path;
  wrapper/documentation discrepancies, SDrive dual-TTL behavior, exposure floor.
- REQUIRES OPERATOR-WORKFLOW VALIDATION: strict dark provenance/recapture UX and
  configuration_id maintenance; no automatic temperature/age validity implemented.
- REQUIRES DESIGN DECISION: cross-process exclusion mechanism if simultaneous
  standalone use must be supported; process-local reservations alone are insufficient.
- OPEN: native-call abort/deadline feasibility; do not promise forced cancellation.
- OPEN: real profile schema for all instruments and persistent-worker reservation
  bridge details. Direction is fixed; bounded phases resolve implementation details.
- Environment gap: no PyQt6/ruff/uv.lock/vendor tree here; no locked Windows test.

## Deployment guidance checkpoint

[Lab-PC deployment](lab-pc-deployment.md) is now documented as a proposed manual
release procedure. It is not an implemented auto-updater or production installer.
No new acquisition phase is complete: [Qt gate](qt-gate-status.md) reran with
15 passed / 4 skipped; full suite 318 passed / 4 skipped. Collision-safe map allocation
is still PLANNED/BLOCKED pending executed QtWidgets acceptance. Do not infer a pass
from a committed test file, bytecode file or pytest exit code with skipped modules.

## Device-wrapper audit checkpoint

[Audit](device-wrapper-audit.md) covers every devices/ module and the first-party
consumer inventory. [Repair plan](device-wrapper-repair-plan.md) supersedes the matrix
as the detailed failure-path task order, without retiring public APIs or certifying
hardware. Most wrappers need targeted repairs; IDQ/DLT merits staged internal ownership
redesign, not a wholesale command rewrite. P0 histogram eval parsing requires fixtures.

The next independent wrapper task is W1 ITC transport lifecycle only. Keep it separate
from the acquisition lane: the QtWidgets gate remains unmet (15 passed / 4 skipped),
so collision-safe map allocation remains planned/blocked. Full suite 318 passed /
4 skipped. No production/test Python changed in this checkpoint. Phase 7 launcher,
persistent HORIBA connections and streaming migration remain unimplemented.

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
