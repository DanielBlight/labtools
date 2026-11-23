# Workspace hub and all-hardware implementation evidence, 2026-11-23

Status: engineering evidence; Windows and connected all-hardware acceptance pending.

## Exact baseline

The supplied clean feature/unified-gui-alignment snapshot is commit
560eeb3a17180aaabe19890b7f5e89d74ef1abe2. All 401 bundled entries were decoded and
verified against declared byte sizes and SHA-256 hashes. The working unified
alignment source was used directly, not reconstructed from earlier patches.
The user reported the preceding integration worked; no new per-device hardware
pass, dark-subtraction pass or active-close pass is inferred from that statement.

## Implemented scope

Workspace is now an operator configuration/status hub: source/mode/local-profile
summary, explicit device-test shortcuts, last-observed device status, source-bound
workflow settings export/import, startup preferences including alignment, and
idle-only source-configuration switching. Hardware profile/limit editing remains
separate. Settings cannot activate outputs, change backend/identity or inject
hardware fields. Wrong source fingerprint/backend/identity and duplicate JSON keys
are rejected. Import validates all drafts before applying and restores the previous
controls on application failure. Configuration switching builds a valid same-mode
replacement before closing the old window, and is refused during active work or
while the real laser remains connected. Simulation is never silently switched to real.

The explicit --hardware route binds the existing real map adapter, existing shared
spectrum/alignment worker, existing Annealing acquisition, asynchronous real ITC4000
controls and existing camera selector. Default-disabled, --hardware-spectrum and
--simulate routes remain. No automatic Connect all, output ON, shutter open or motion
is performed on launch. Devices remain operation-scoped where that is their existing
lifecycle. Map test closes the SPAD gate but does not scan or establish count-input
acceptance. Shutter/stage diagnostics are worker-bound and hold the Annealing lease.
A running native diagnostic is not forcibly interrupted; parent close waits for it.

The ITC4000 service owns its connection on one worker thread. Connect only reads
identity/output/current; Apply and ON are explicit, optical-lease-serialized commands.
The real current policy is the existing 0.040 A maximum/threshold from the working
map GUI, not the synthetic 0.080 A default or 0.100 A ceiling. No limit is widened.
OFF/disconnect remain available during acquisition/faults. Stop all queues diode OFF.
Close queues disconnect and waits; a failed disconnect/startup cleanup retains its
handle/lease for retry and never reports a false disconnected state. No TEC controls
or new laser power model are added. Existing wrapper close behaviour is unchanged.

Annealing requires the existing valid reviewed local flat instrument profile.
Source/local mirror/open-time limits are intersected. The explicit profile is passed
to the existing acquisition validator without changing global environment variables.
The acquisition algorithm/cleanup ordering is unchanged; an optional profile argument
is added to the validator and run entry point. Existing one-argument validation and
standalone behaviour remain compatible. build_config now imports its data contract
from config.anneal_types rather than importing native acquisition modules merely to
construct a validated draft. No profile migration, generated approval, schema change,
dependency/lock change, SDK change or package-version bump is included.

One workspace reservation authority is retained. The laser gets a separate controller
connection resource and temporarily reserves shared optical resources for Apply/ON.
A stable already-selected output can be used during a measurement. Map/Annealing/
diagnostic operation failures block further hardware work until application teardown;
laser OFF/disconnect remain available. Existing spectrum worker faults remain shared
between range/alignment. This is not a cross-process lock, emergency stop or physical
interlock. Existing first-discovered device-selection limitations remain documented.

## Actual validation

Final targeted run: **630 passed, 317 warnings in 99.96 seconds**. No failures or
skips in that run. It used the standard project conftest/QApplication fixture and
36 modules covering the new hub/hardware paths plus existing alignment, range,
map transport, native gates, simulation, ownership, Annealing cleanup/profile/startup,
and ITC4000 contracts. Warnings were Matplotlib/Pyparsing deprecations.

Twenty new tests cover lazy driver-free composition, explicit CLI modes, map leases,
laser read-only connection/current limits/thread affinity, optical exclusion,
OFF during acquisition, disconnect/startup-cleanup failures, profile enforcement,
source/local profile validation, the actual Annealing acquisition pipeline with fake
native devices, shared hardware fault refusal, settings identity/limit rejection,
actual Qt controls, Stop all, deferred close, retry after failed laser disconnect,
settings round-trip/startup alignment restore, map diagnostics and configuration
switching/refusal. All device transports used for acquisition tests were fake.
No physical device was connected in this environment.

Changed-file Ruff check --fix passed on all 19 changed/new Python files using the
repository configuration and Ruff 0.16.3. compileall passed. Local documentation
file-target checks passed. The full project test suite, build/wheel, hosted CI,
Windows rendering and connected hardware were not run here.

Environment: Linux, Python 3.12.16, PyQt6/Qt 6.7.1, Matplotlib 3.8.4,
NumPy 1.26.4, pytest 9.2.0. Python-only LabJackPython, PySerial and PyVISA packages
were installed in the isolated test environment to import existing fake-device
regressions; no native driver or hardware was used and no repository dependencies
were changed. This is not the locked Windows runtime.

The container lacks desktop GL libraries. Actual offscreen raster Qt tests used
temporary loader libraries linked to existing Chromium ANGLE GLES/EGL, with GLX
entry points that abort if called. No GLX entry point was used. This is not shipped
and does not mock Qt widgets, event loops or QThreads. It establishes offscreen Qt
behaviour, not OpenGL/Windows/vendor-driver acceptance.

Actual idle all-hardware-mode Workspace/Laser captures were reviewed at 1400x850.
They are application screenshots, not generated concept images. The source manifest
wrap/layout was corrected during review. No hardware was constructed for capture.
Windows font/platform rendering can differ.

The updater was tested against an exact baseline copy: preflight without writes,
all-target conflict refusal, CRLF-normalized baseline acceptance, complete application,
exact installed bytes, repeat application, rollback and refusal to overwrite later
edits during rollback. Validation subprocess streaming/nonzero-exit and fail-fast
command assembly were tested separately; stub runner results are not pytest passes.

## Remaining connected evidence

Use docs/workspace-hardware.md for the lab-PC order. Record exact commit, source
configuration, local profile, computer, per-device observations and tracebacks.
Connect/readback is separate from powered Output ON or an Annealing run. Mark
unperformed checks Not tested. Existing standalone acceptance is not relabelled.
Do not deliberately unplug powered hardware to reproduce fake fault tests.

## Next bounded continuation prompt

Continue from the applied Workspace hub/all-hardware implementation on the current
feature branch. Inspect actual Git HEAD/status, current-state, release-plan,
workspace-hardware.md and this evidence note before editing. First read the Windows
validation output and simulation/settings rehearsal. Do not replay old alignment
installers or reconstruct current files from earlier patches. If a failure exists,
fix the demonstrated cause in one bounded change without weakening assertions,
extending deadlines, widening limits or adding delays to real acquisition. After
Windows validation, commit/push and test the explicit --hardware route on the lab PC
at that exact commit using the existing reviewed local Annealing profile. Record
Workspace settings/configuration behaviour; spectrum/alignment handoff and exclusion;
small map/gate cleanup; SC10/stage diagnostics; minimal Annealing Stop/close cleanup;
ITC4000 Connect/readback separately from intentional Output ON/OFF at the preserved
limit; camera preview/dark; Stop all and deferred close. Keep OFF/disconnect available
on faults and never claim disconnected after failed cleanup. Do not migrate the
strict flat profile, widen the laser policy or redesign unrelated panels in this
checkpoint. After connected results, address only demonstrated operator issues and
consolidate acceptance records before choosing the next release milestone. Deliver
actual test evidence, exact Git staging/commit commands and the next bounded prompt.
