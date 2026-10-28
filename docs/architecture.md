# Architecture

Authoritative current/target design, 27 October 2026. Read [handover](ai-handover.md)
and [conventions](development-conventions.md) before implementing a roadmap phase.
Historical batch notes explain past changes, not current completion status.

## Status vocabulary

- **CURRENTLY IMPLEMENTED AND VALIDATED** means offline software tests passed in
  the recorded environment, not that physical hardware was validated.
- **CURRENTLY IMPLEMENTED BUT REQUIRES HARDWARE VALIDATION** identifies real paths.
- **AGREED TARGET DESIGN** is the chosen direction, not available functionality.
- **PLANNED BUT NOT IMPLEMENTED** identifies migrations/features still absent.
- **OPEN**, **REQUIRES DESIGN DECISION**, **REQUIRES HARDWARE VALIDATION** and
  **REQUIRES OPERATOR-WORKFLOW VALIDATION** identify remaining evidence/decisions.

## Current repository after this batch

The snapshot contains 99 exported files, on feature/shared-instrument-session,
reported HEAD 385df0dbfbc58f61200030c6165238404d92bed2, with uncommitted shared-map
work. That work is part of this baseline, not newly delivered by this batch.
There is no original .git directory, lockfile or vendor tree in the export.
Alignment appears in the HEAD..main difference report but NOT the file manifest
or file bodies. Its implementation cannot be recovered from this snapshot.
Do not overwrite the laboratory main branch or fabricate that missing code.

### CURRENTLY IMPLEMENTED AND VALIDATED: offline boundaries

- cli.py and launchers.py lazily dispatch existing standalone tools. Help does
  not import Qt/native drivers. launchers.py is not a shared application.
- config/ contains intensity-map configuration and strict annealing recipes /
  maintainer profiles. config/recipe_ui.py remains a Qt compatibility shim.
- acquisition/intensity_map.py owns the resumable loop, cooperative point-boundary
  cancellation, checkpointing and independent checkpoint/home/gate cleanup.
  Optional device_provider injection already exists in the supplied baseline.
  IntensityMapConfig/SCHEMA_VERSION remain re-exported from acquisition; schema is
  still 1. runtime.map_devices retains its real ExitStack order and explicit
  synthetic-state context; io remains only a partial home for legacy outputs.
- runtime/session.py owns process-local atomic exclusive whole-job reservations,
  direct aliases and lazy connections on one persistent synchronous worker.
  Resource failures latch faults. Only explicitly allowlisted argument-free
  cleanup may run after a fault. Release does not disconnect. Active leases
  prevent shutdown. Existing standalone windows do NOT use this session.
- runtime/labjack_service.py and shared_map.py already provide opt-in mirror/gate
  service adapters. Mirror and gate reserve the same physical LabJack. IDQ stays
  per-map on the acquisition thread and is NOT globally coordinated.
- simulation/map_devices.py provides the existing shared-per-map synthetic state,
  deterministic coordinate/channel seeding and backend-specific resume checks.
- processing/ owns Qt/native-free combination, background and dark arithmetic.
  range_spectrum.py preserves legacy imports and loads vendor stitching lazily.
- NEW config/spectrum.py, acquisition/spectrum_service.py, runtime/spectrum_backend.py,
  simulation/spectrum.py and io/spectrum_records.py provide the opt-in headless
  spectrum service, provenance-bearing darks, explicit real/synthetic composition
  and pickle-free versioned archives. The representative workflow is
  examples/experiments/simulate_spectrum_service.py. No GUI migration is claimed.
- NEW LabJackU6 startup cleanup closes a returned U6 if calibration/delay fails,
  preserves the primary exception and makes successful close idempotent.

### CURRENTLY IMPLEMENTED AND VALIDATED: Phase 2 shared composition
runtime/shared_application.py owns one process-local InstrumentSession and injects a narrow manual service plus SharedMapProvider-backed acquisition into the existing windows. Manual connect reserves only and remains lazy; disconnect/close releases only its lease. Shared-map mode disables laser controls because ITC ownership is not coordinated. Detached status records report available/busy owner/faulted/closing/closed and connected state without exposing handles or authorizing calls. Standalone launch composition remains unchanged.

### CURRENTLY IMPLEMENTED BUT REQUIRES HARDWARE VALIDATION

Real wrappers, shared LabJack service and the new real range adapter. The adapter
calls existing connect/configure/range/dark/disconnect APIs without changing SDK
commands, presets, voltage limits, acquisition order or successful timing.
The LabJack failure-path fix adds a close attempt, not movement or gate commands.
No physical device was used. See [roadmap](refactor-roadmap.md) for known defects.

### PLANNED BUT NOT IMPLEMENTED

Complete shared launcher, central IDQ ownership,
shared-session synthetic map composition, persistent HORIBA asyncio worker,
GUI use of SpectrumService/DarkRecord, alignment integration, general operator
recipes/profiles, camera/laser/shutter/stage simulation and legacy cleanup review.

## Dependency direction and module placement

Composition (runtime factories, future application root) chooses implementations
and injects dependencies into acquisition/services and GUI controllers.
GUI -> acquisition/service contracts + config/data; acquisition -> processing +
config + narrow contracts; runtime adapters -> wrappers + acquisition APIs;
wrappers -> vendor SDKs. simulation -> config/data/processing, never native drivers.
io -> data records/config, never GUI. The current spectrum records live beside
their service; move only if an actual dependency cycle requires a data package.
No acquisition module imports runtime/spectrum_backend.py. No wrapper imports GUI.
Existing map config -> simulation model-version dependency is retained, not a new
pattern to spread. Existing large windows remain legacy migration boundaries.

## Instrument contracts and lifecycle: AGREED TARGET DESIGN

Use structural Protocols for capabilities consumed by a real workflow. Keep the
existing Mirror/Gate/Counter protocols and new RangeBackend; do not create a
universal instrument ABC. A gate's close means output action, not disconnect.
A service resource must expose close() for InstrumentSession. Async backends use
an async context factory; do not force synchronous lifecycle methods onto them.

New wrappers validate construction parameters before opening where possible;
construction is normally inert, connect is explicit, connection state describes
owned handles rather than certifying reachability. Existing eager LabJack/ITC
constructors remain compatible until adapted at factories. Wrappers contain SDK
objects, commands, units, readback checks and vendor error translation. Preserve
causes; add context without swallowing errors. Document owner thread/loop where
supported by evidence. No arbitrary new timeouts, limits or safe-state commands.
Factories clean partial startup before returning. Wrapper close attempts all
independent releases and reports failures; successful close is idempotent. Failed
close must not be reported as a known physical safe state. Context managers must
preserve a primary failure and attach cleanup failures. Legacy wrappers do not
all meet this target yet; the migration matrix is explicit about that.
Logging belongs at useful boundaries with device/operation context, never secrets
or per-poll spam. Retain existing loguru/stdlib logging; no global configuration
inside reusable modules. Application-level log routing is a later composition task.

## Ownership and application lifecycle: AGREED TARGET DESIGN

One application composition root owns sessions and approved profiles, not a global
singleton. Resource keys represent physical connections, not GUI windows. Reserve
all required resources atomically for a complete operation and its cleanup.
Default exclusive access; any shared-read exception requires device-specific
proof. Visibility of two tools is not permission for concurrent hardware commands.

Keep the synchronous session for reviewed synchronous services. Do not put HORIBA
coroutines on that worker or reuse objects across AsyncTaskRunner's fresh loops.
A future persistent asyncio worker owns HORIBA connect/use/disconnect on one loop,
serializes whole jobs and exposes data-only futures/signals. Its reservation
integration must cover both detector presets sharing ICL/monochromator, not just
individual CCDs. This worker is planned, not present.

Tool close cancels its job and waits for cleanup/lease release; it does not close
an application-owned connection. Application shutdown rejects new work, requests
cooperative stops, waits for jobs, runs reviewed cleanup and closes resources on
their owning worker. Blocked native calls remain a limitation, not something a
mutex or Python cancellation can forcibly fix. Report unavailable/busy/faulted/
closing states separately; do not auto-reconnect a fault or silently simulate it.
Process-local reservations do not exclude other applications. Operators must not
run standalone tools against the same device concurrently.

## Canonical spectrum/dark service

CURRENTLY IMPLEMENTED AND VALIDATED in the opt-in service, not legacy GUIs:

1. SpectrumSettings validates finite positive exposure/slit, normalized increasing
   range, integer tokens/counts and existing reduction rules. The real wrapper
   still enforces its own preset limits; this service does not override them.
2. Each service operation opens/configures/uses/closes one backend context on its
   caller's asyncio loop. There is no persistent connection or resource manager
   hidden in SpectrumService. Concurrent real service calls are NOT coordinated.
3. none acquires signal without subtraction. per_center/per_frame delegate the
   existing range/wrapper capture order and reduction math unchanged.
4. capture_dark produces an immutable owned DarkRecord with settings, UUID and
   timezone-bearing capture timestamp. A stored dark is not an enable flag.
5. pre_taken requires exact SpectrumSettings equality BEFORE opening hardware,
   then matching finite 1D shapes and wavelength axis at existing 1e-8 nm absolute
   tolerance. No interpolation, exposure scaling, clipping of negative results,
   silent raw fallback or automatic replacement dark is performed.
6. Every settings field participates, including frame reduction/count, overlap,
   backend and configuration_id. This is deliberately conservative. A change
   invalidates reuse; switching subtraction off retains the record for later
   explicit use with matching settings. No mutable service dark cache exists.
7. configuration_id is a required maintainer context identifier for preset/ROI/
   grating/calibration changes not represented by fields. It is NOT an observed
   temperature, verified calibration or safety attestation. Operator/hardware
   validation remains necessary; no automatic age/temperature expiry is claimed.
8. Result intensity is the requested display/export data. raw_intensity is kept
   for none/pre_taken. Fresh-dark reductions do not expose raw frames in the
   legacy API; raw_intensity is None, never reconstructed after nonlinear math.
9. Cooperative cancellation checks occur before opening and after a whole backend
   operation. Context cleanup completes before cancellation escapes. This is not
   per-frame/centre cancellation or a native abort implementation. Acquisition,
   shape and calibration errors propagate; failed results are not published.
10. io/spectrum_records.py stores strict schema-v1 dark NPZ archives with JSON
    metadata and allow_pickle=False; result exports include settings, correction
    mode, dark identifier, raw availability and synthetic_data. Exclusive create
    prevents overwrite; ordinary write failures remove partial files. Abrupt
    process/power failure may leave a partial archive. No result loader yet.
    Legacy DarkSpectrum CSV remains unchanged and lacks provenance. Do not attach
    current settings to a loaded CSV and pretend they describe its capture.

Legacy spectrum GUI still uses DarkSpectrum and only axis checks; settings
changes can leave stale darks. It allows two median frames although the wrapper
requires three. Its worker bookkeeping and disconnect warning suppression need
separate Qt/lifecycle review. Those problems are NOT fixed by an opt-in service.

## Alignment: AGREED TARGET DESIGN / OPEN evidence

Repeated alignment uses the same acquisition/correction policy, not a second dark
implementation. A future persistent worker avoids reconnecting each frame; use a
bounded latest-result channel rather than unbounded Qt signals. Stop cooperatively,
finish cleanup, then release ownership. A stored dark may be reused only under
matching settings; fresh-dark cadence must be explicit, not hidden in a GUI timer.
The requested 0.02 s alignment floor conflicts with the uploaded wrapper's
configure() minima: 0.065 s Syncerity and 0.100 s Symphony. Preserve these values.
REQUIRES HARDWARE VALIDATION and review of the missing main-branch alignment code
before deciding the supported live-acquisition floor. Do not bypass configure().

## Configuration: AGREED TARGET DESIGN with annealing precedent

- Maintainer profiles: connection identity, wiring, approved limits, calibration /
  configuration IDs, allowed capabilities. Existing anneal profile uses protected
  machine installation and LABTOOLS_INSTRUMENT_PROFILE development override.
- Operator recipes: experiment ranges, dwell/exposure, channels and output choices
  within profile limits. Strict JSON schema, finite values, reject unknown fields.
- Preferences: per-user QSettings layout/display and convenience values; preserve
  existing keys. Never persist output-enabled state or safety acknowledgement.
- Session state: connections, leases, faults, dark records and running jobs; do not
  restore these from preferences as if hardware were connected or safe.
- Secrets/machine details: external deployment configuration, not source or recipes.
  Existing IP/VISA defaults are retained; no credentials were added. Examples are
  unapproved templates, not calibration. Do not commit data, profiles containing
  secrets, .venv, caches, vendor binaries or migration backups.

## Safety and cleanup

Preserve reviewed measurement-specific ordering. Map cleanup remains checkpoint ->
home -> gate close, independently attempted before release. Home is zero voltage,
not universally safe. Shared LabJack shutdown gate-close is already an opt-in
baseline behavior, not a new manual-GUI disconnect behavior. ITC close releases
VISA but does not disable emission; SC10 close releases serial but does not prove
shutter closure. Software output commands/readbacks cannot certify an optical path.
Laser/shutter/stage restoration policies require explicit workflow review.
Do not automatically run diagnostics, legacy hyperspectral scans or hardware tests.
Software never replaces laboratory procedures, physical interlocks or beam checks.

## Decisions and alternatives

### ADR-01: retain existing session, no second universal manager
Context: baseline already has reservations/fault cleanup. Alternative: replace
with a universal device ABC/global singleton. Reason: avoid duplicate ownership
and widespread unvalidated migrations. Consequence: adapters are incremental;
legacy tools remain outside coordination. Validate shared GUI shutdown later.

### ADR-02: capability protocols, not uniform wrapper inheritance
Alternative: force all devices into connect/read/close. Reason: async HORIBA,
borrowed gate/mirror and streaming IDQ have different lifecycles. Consequence:
contracts grow only with consumers. Real/fake adapter tests share service behavior;
SDK conformance still requires hardware.

### ADR-03: per-operation spectrum lifecycle first
Alternative: cache HORIBA immediately. Reason: current Qt runner uses fresh loops
and no Qt runtime is available here. Consequence: reusable headless service now,
no live-performance claim; persistent worker and GUI integration are later phases.

### ADR-04: strict provenance-bearing darks, legacy API retained
Alternative: infer CSV settings or scale exposure. Reason: axis equality alone
cannot establish acquisition compatibility. Consequence: new service rejects
unverified legacy darks; old APIs unchanged. Conservative full-settings equality
may require extra captures. REQUIRES OPERATOR-WORKFLOW VALIDATION for GUI migration.

### ADR-05: explicit synthetic adapter, never fallback
Alternative: GUI-specific fakes or auto-simulation after failure. Reason: exercise
one service path and keep measured/synthetic provenance distinct. Consequence:
toy model validates software only; it has no SDK, noise, timing or stitching model.

### ADR-06: no invented raw data
Alternative: add dark back to reduced corrected output. Reason: nonlinear frame
combination is not invertible. Consequence: fresh-dark result exports mark raw
unavailable until a reviewed low-level result API exposes actual raw frames.

### ADR-07: bounded additive slice instead of untestable GUI rewrite
Reason: baseline passes offline tests but Qt is unavailable, alignment absent and
real limits conflict with requested live floor. Consequence: legacy GUI dark issue
remains explicit. Next task is service migration under fake Qt tests, not a new
architecture. See roadmap for acceptance gates and remaining OPEN items.

