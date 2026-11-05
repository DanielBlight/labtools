# Device-wrapper repair plan and development guidance

## Current-setpoint readback contract review (2026-11-05)

**Decision recorded, NOT implemented:** after get_current returns in set_current,
reject a nonfinite readback with RuntimeError before tolerance arithmetic. Include
requested amperes and the observed nonfinite value in the diagnostic. Preserve
finite tolerance, existing mismatch text, query/conversion exceptions and W1 cleanup.
See [readback contract](itc4000-readback-contract.md) for evidence and compatibility.

Authority: labtools_source_20261105_131803.txt, HEAD
013afc9fa6d7b6181de571ffe911383071eaf9ec, branch feature/shared-instrument-session,
upstream +6/-0, clean tracked worktree/index. W1b is committed and all eight W1b
payloads match the implementation backup. Its Windows lint.log/targeted.log/XML
are listed but not exported; their outcomes are not inferred from commit or hashes.
No supplied W1b acceptance failure is demonstrated. New sandbox baseline: 140 passed.

Final targeted characterization: 178 passed (38 new, 96 W1b, 44 lifecycle), zero
failures/errors/skips, 32.91 seconds. Ruff attempt failed to start: No module named
ruff. Local lint remains required. No production or existing test changes; no native
VISA, hardware, actual sleep, physical outputs, full-suite or Qt execution.

Observed current behavior: NaN readback can evade mismatch; positive/negative infinity
mismatch; malformed text raises ValueError after the current write. The recommended
check is post-write verification, not a pre-write interlock. get_current remains raw
float conversion under this decision; direct GUI reads and their second post-set
query are outside the proposed setter-only change. No retry, output-off, new close,
transport fault state, tolerance, enable sequencing, delay or timeout policy change.

Next bounded task: implement only the recorded setter readback guard, revising both
new and existing NaN-readback expectations while retaining finite/tolerance/conversion
and cleanup coverage. ID900 stays deferred with its return instructions unchanged.
This section supersedes earlier next-task pointers for readback scheduling only;
historical W1b and acceptance records below remain scoped to their original evidence.

## Current W1b implementation checkpoint (2026-11-05)

**Constructor/current/temperature finite checks are implemented and fake-transport
validated. Local lint and Windows execution remain unverified.** This section
supersedes historical statements that W1b is only a decision or unimplemented.
It does not broaden W1b into complete finite-input safety or physical acceptance.

Authority: labtools_source_20261105_125159.txt, created UTC
2026-11-05T12:51:59.3162870Z, HEAD 3e41ca827913e022a981b9010d34d82c6dec3a55,
branch feature/shared-instrument-session, upstream +5/-0, tracked worktree/index
recorded clean. The corrected fixture import and _fake binding are the baseline;
no corrected local lint/pytest transcript is supplied. Preserve the original
contract installer backup and separate lint-fix backup; do not restore old payloads.

After both constructor float conversions, math.isfinite checks reject nonfinite
threshold_current and max_current with field-specific ValueError before VISA opens.
Current and temperature setters reject nonfinite converted requests before transport.
Existing bounds, defaults, float coercion/conversion exceptions, units, .9g formatting,
successful command/query order, readback tolerance and W1 cleanup remain unchanged.
No new temperature limit, type whitelist, bool/string rejection or output-off policy.

Fresh baseline: 97 targeted cases passed. Final implementation: 140 passed, comprising
96 finite-contract cases and all 44 unchanged lifecycle cases; zero failures/errors/
skips. All original 53 finite-contract parameter cases remain covered with affected
expectations revised; 43 cases were added. Final duration 26.19 seconds. Tests use
isolated fake PyVISA; sleep/output-enabling paths are stubbed where characterized.
Ruff attempt exited 1: No module named ruff. Offline tool-cache lookup also found no
Ruff. No dependencies were installed; local lint is required before commit.

Only the wrapper, its finite-contract test and six documents change. AST checks
confirm all other production methods are identical; the three changed methods differ
only by the four finite guards. The import of math is the only other source change.
Existing lifecycle tests, callers, schemas, dependencies, limits, simulation and
plotting are unchanged. No full-suite, GUI, native VISA, network or hardware execution.

Enable sequencing/preflight, TEC delay, timeout, nonfinite readback/tolerance and
public-attribute mutation remain excluded and unfixed. Finite temperature extremes
remain accepted by policy, not approved for hardware. A finite current request can
still receive NaN readback without mismatch; enable may still perform TEC work before
current rejection. Pulse methods and other wrappers are unchanged, not certified.
ID900 histogram work remains deferred, P0 open, with its return instructions intact.
No original full-audit, operator-visible, native-SDK or hardware acceptance is claimed.

Next bounded task: review the ITC4000 current-setpoint nonfinite-readback contract
only, using fake replies; record a decision before implementation. Do not combine
with enable sequencing, delays, timeout, output-off policy or ID900 work.

See [W1b contract and implementation](itc4000-finite-input-contract.md).
Historical sections below retain earlier evidence and are not current gate results.

## ITC4000 W1b contract decision (2026-11-05)

See [finite-input decision](itc4000-finite-input-contract.md). Current behavior is
characterized; production validation is NOT changed. Decision for a separate next
checkpoint: retain float coercion, reject nonfinite constructor threshold/ceiling
before opening VISA and nonfinite current/temperature before setter transport;
preserve existing bounds, defaults, units, command order and W1 cleanup.

97 targeted cases passed (53 new, 44 existing), zero failures/errors/skips.
Ruff could not execute because the module is absent; local lint remains open.
Enable sequencing/delay, timeout and nonfinite readback policy remain separate
unfixed questions. No new safety limits or automatic output-off policy is introduced.
ID900 histogram work stays deferred with its return instructions preserved.
This section supersedes earlier next-task pointers for W1b scheduling only.

## Scheduling decision: ID900 histogram work deferred (2026-11-05)

The maintainer reports that the device is an **IDQ ID900 Time Controller**, but
response records and further device details are not currently available. This is
user-supplied model identity, not verified firmware or response-format evidence.
Defer the IDQ histogram fixture/parser work until those inputs are available.
**DEFERRED / BLOCKED ON EVIDENCE; P0 eval(raw) remains open and unfixed.** This is
not risk acceptance, parser approval, or hardware/native-SDK acceptance.

Do not keep selecting fixture collection as the next engineering checkpoint while
these inputs are unavailable. See [return instructions](idq-histogram-fixture-readiness.md#return-to-this-work)
for the evidence checklist and reopening procedure. Older fixture-collection next-task
pointers below are historical and are superseded by this scheduling decision.

Next independent checkpoint: ITC4000 W1b finite-input contract review only. Inspect
the current constructor/setter validation and existing tests, document compatibility
and one bounded design decision, but do not implement policy or access hardware.
This is separate from IDQ parsing, not a claim that the IDQ issue is resolved.

## IDQ histogram fixture-readiness checkpoint (2026-11-05)

**BLOCKED on authentic, provenance-recorded response fixtures.** See
[fixture-readiness decision](idq-histogram-fixture-readiness.md) for exact code/caller
references, vendor-example inventory, supported boundaries and unknown grammar.
The current eval(raw) path remains P0 and unfixed. Vendor examples are not response
fixtures. No parser replacement, SCPI change, hardware access or application gate
rerun is part of this documentation-only checkpoint.

Authority: labtools_source_20261105_113246.txt, HEAD
c52badae636ba8214bfeea7733600ab3cff35181, branch
feature/shared-instrument-session, clean tracked worktree/index, upstream +2/-0.
Owner-contract documentation is committed; its test has an AST-equivalent import
wrap relative to the installed backup. Preserve that edit. No local owner-checkpoint
verify/Ruff/pytest transcript or v4 raw-artifact verification output is supplied.

Next bounded task: assemble and review a provenance-recorded fixture bundle from
already approved records/specifications. Do not automatically collect hardware
responses, execute response text, invent fixtures or implement a parser while blocked.
This section supersedes older next-task pointers only for fixture readiness; all
historical acceptance limitations and independent wrapper backlogs remain intact.

## Decision and boundaries

This is the staged repair plan. W1 transport lifecycle is now implemented and offline-tested; remaining tasks are proposed, not completed rewrites. Read the
[evidence audit](device-wrapper-audit.md) first. The current input is snapshot HEAD
`ceaabec9ea4882c1882f71facf604a04099a5992`. The QtWidgets acquisition gate remains
unmet; do not implement map-directory allocation or launcher changes on the strength
of committed test source or skipped tests.

The user's additional wrapper request permits an independent audit/repair lane. Keep
one wrapper/failure boundary per checkpoint. Do not mix wrapper repairs with map
allocation, persistent HORIBA connections, IDQ streaming migration, GUI redesign,
profile expansion or repository-wide formatting. No universal device base class or
second resource manager is justified. InstrumentSession remains the process-local
reservation authority; wrappers do not create global caches.

## Priority and sequence

1. **P0 IDQ histogram parser:** replace eval only with a fixture-backed, bounded grammar.
   Obtain representative response text from already available approved records/vendor
   documentation. Do not contact an instrument to gather it during this task. If fixtures
   are unavailable, record the blocker and restrict untrusted histogram use; do not
   invent accepted syntax. This is urgent and separate from transport/stream work.
2. **W1 ITC transport lifecycle: implemented/offline-tested; physical acceptance open.** Repair
   partial construction and teardown/error preservation. No new output commands.
3. HORIBA partial startup and independent cleanup on the owning loop; no optical changes.
4. DAC two-axis preflight and explicit partial-write diagnostics, preserving encoding.
5. UC480 partial acquisition startup/cleanup; retain frame ownership and existing close aggregation.
6. SC10 serial lifecycle/transcript coverage; preserve toggle/state semantics.
7. IDQ count transport cleanup/timeouts, then DLT process/thread ownership in separate commits.
8. Kinesis finite/native-unit validation, then LabJack context/closed-state guards.
9. SPAD borrowed-device/pin tests and documentation; no rewrite required.

If the parser fixtures become available, prioritize that P0 checkpoint rather than
silently continuing lower-priority cosmetic work. Do not use the lack of fixtures as
permission to keep eval for new consumers. No runtime deprecation/disable switch is
implemented by this documentation checkpoint.

## Compatibility contract before any change

Inventory all first-party imports, dynamic factories, external scripts known to the
maintainer and tests. The audit's AST inventory is a starting point, not a complete
external API inventory. Freeze public class/method signatures, import paths, return
shapes/dtypes, callback ordering, command strings/order, units, limits, timeouts and
physical state semantics. Add success-path transcript tests BEFORE changing failures.

Keep distinct meanings of close:
- ITC/LabJack/SC10/Kinesis/camera: transport/device release as currently documented.
- SPADGate.close: physical gate-low command on a borrowed LabJack.
- ScanningMirror.home: two zero-voltage writes, not a certified safe state.
- HORIBA.disconnect: device/manager teardown on the owning asyncio loop.
- IDQ disconnect/stream stop: separate owned socket/process/thread lifecycles.

Do not add laser-off, TEC-off, shutter-toggle, stage-home or mirror-home to transport
close. Such behaviour belongs to an explicitly reviewed workflow/safety policy. Never
change a unit or invent calibration, travel limits, timeouts or firmware commands.
Preserve Syncerity 0.065 s and Symphony 0.1 s exposure minima. Keep profile/QSettings,
map schemas/resume signatures and deterministic simulation unchanged.

## Standard failure contract

- Validate pure inputs before opening a transport or issuing a command.
- Track handles actually acquired; clean up only those handles. Do not construct or
  reconnect a device merely to clean it up.
- Attempt independent cleanup stages even when one fails. Do not return healthy status
  after a swallowed cleanup failure. Record uncertainty without claiming physical state.
- Preserve the original operation/body exception as primary. Attach cleanup failures
  with structured cause/notes; when no primary exists, raise a clear cleanup exception
  retaining all ordinary failures. Do not wrap CancelledError/KeyboardInterrupt into
  an ordinary ExceptionGroup or convert cancellation into success.
- Broad BaseException handling is justified only at startup/ownership boundaries to
  clean up and re-raise. Do not blanket-catch command failures and continue.
- Define successful-close idempotence, failed-close ownership and retry policy explicitly.
  A failed close must not imply a resource was released. Never auto-reconnect after fault.
- Keep native/loop-affine creation, use and close on the same owner thread/loop.
- Do not claim bounded shutdown for a vendor call that can block. Deadline policies
  require device-owner review; no force-kill threads or speculative retry of toggles.

## W1: ITC transport lifecycle (implemented; physical acceptance open)

### Files and consumers

`src/labtools/devices/itc4000.py`; add `tests/test_itc4000_lifecycle.py` (proposed).
Review `runtime/lazy_devices.py`, `acquisition/run_hyperspectral_scan.py`, map-device
composition and all references to ITC methods. Do not execute the legacy hyperspectral
workflow. Native imports may be stubbed in an isolated subprocess or injected factory;
avoid importing/connecting real PyVISA in the tests. Preserve the existing constructor
API unless an optional keyword-only test seam is clearly justified.

### Implementation

Initialize resource ownership before acquisition. Cover ResourceManager creation,
open_resource, termination configuration and initial *CLS with a cleanup boundary.
On failure, close every successfully acquired handle without replacing the primary.
Normal close attempts instrument and manager independently and preserves both failures.
Context exit preserves a body exception if close also fails. Define whether failed
close retains a handle or latches fault; do not silently report success or retry commands.
Successful close remains idempotent. No command/readback/timeout/default-limit changes.

### Required fake tests

- ResourceManager creation fails: no phantom handle cleanup.
- open_resource fails: manager close attempted once.
- write/read termination setup fails after open: both handles attempted.
- initial *CLS fails: both handles attempted, original failure retained.
- each cleanup stage fails alone and together: later stage still attempted.
- context body plus cleanup failure: body remains primary with cleanup details.
- successful close twice; use-after-close policy; no extra output/TEC/current commands.
- successful constructor/identify/control transcript unchanged, one VISA session.
- factory/close execute on the caller's existing owner thread, no new background owner.

Finite constructor/setter validation is a separate W1b behaviour checkpoint. Do not
bundle new laser safety policy or automatic diode/TEC-off with W1. Before release,
maintainer performs supervised real-device transport acceptance and checks output
state policy; offline fakes do not certify emission safety.

## W2: HORIBA lifecycle (implemented; physical acceptance open)

Add fake SDK manager/CCD/mono tests importing the actual wrapper in an isolated
namespace/subprocess. Existing adapter fakes are insufficient. Fail manager.start,
mono.open, ccd.open, identity/configuration, acquisition, ccd.close, mono.close and
manager.stop independently and in combinations. Include CancelledError at each await.
Assert independent cleanup, preserved primary/cancellation, no repeated physical open
on failed close, and loop/thread identity. Keep optical command sequence and delays.

Do not change _wait_for_* deadlines in this commit. Follow with a reviewed timeout
policy only after valid operation-duration evidence. Direct exposure setter validation
and cache-after-success are another narrow task, preserving detector minima and units.

## W3: IDQ parser and count transport

### Parser checkpoint

Freeze accepted firmware response fixtures and expected int64 arrays/bin-axis identity.
Specify allowed delimiters, whitespace, signs, empty responses, count range and maximum
size. Reject nested/non-numeric/malformed expressions and code-like text without eval.
Use benign rejection fixtures, not executable exploit payloads. A safe parser may be
custom, JSON or literal-based only if fixtures establish that grammar. Add overflow,
boolean/non-integer and oversized-response tests. Keep histogram SCPI ordering and
x-axis construction unchanged. No network or new firmware commands.

### Count transport checkpoint

Inject fake ZMQ context/socket and port-check seam. Test repeated connect policy,
partial context/socket/connect failure, REQ timeout state, independent socket/context
close and primary-error preservation. Review LINGER and reconnect policy explicitly;
do not invent automatic retry. Keep shared count construction/use/close on the session
worker. Update tests so a real-wrapper cleanup failure reaches the session fault
contract rather than disappearing inside a fake adapter. No streaming ownership here.

## W4: DLT ownership redesign

Inventory both dlt_connect and controller launch paths. Preserve public facade and
provide compatibility adapters if return types change. Introduce an explicit owner
for context, socket, process handle and streams; distinguish launched-here from external
service. Replace the stop boolean race with a monotonic stop Event; do not clear it
inside run. Keep join as waiting, with a compatibility transition for old stop-on-join
callers. Capture callback/worker failures and report live threads after timeout.

Tests: stop-before-start, stop-during-setup, partial socket/monitor/poller failure,
callback failure/block, peer disconnect, process startup timeout, terminate/kill/wait
failures, independent cleanup and externally owned service preservation. Use fake
processes/sockets and deterministic Events, no real service launch. Do not change binary
framing/trailing-byte handling without timestamp fixtures and a separate decision.

## W5: DAC/mirror preflight

Use byte-exact EEPROM/calibration and I2C transcript fixtures. Compute/validate BOTH
finite requested values and BOTH representable DAC codes before either write. Do not
clip, rescale or change calibration formulas. Preserve axis A then B ordering and pin
pairing. Test invalid B sends no A write; second transport write failure reports partial
movement without automatic rollback/home. Confirm EEPROM response length/ack policy
from documented format before replacing the 255 heuristic. Physical calibration and
wiring acceptance are mandatory before deployment.

## W6: UC480 and SC10 (separate commits)

Camera: explicit setup/live state, vendor-supported rollback after partial start,
original-error retention on connect/close, independent stop+close attempts, owned frames.
Test setup/start/stop/close combinations and exactly-once teardown. Do not claim camera
close alone is insufficient without SDK evidence. Confirm camera selection separately.

SC10: fake serial transcript tests for open/reset/identify/echo/prompt/timeout/close.
Preserve serial settings and enum values. Retain original connect error if close fails;
define lost-handle/fault state. Never automatically retry toggle_enable or change
physical shutter state on transport close. Physical shutter/trigger acceptance remains.

## W7: Kinesis, LabJack and SPAD (one device per checkpoint)

Kinesis: finite positive timeout and finite position checks before motion, native units,
exactly-one selection, close-failure visibility, no automatic homing. Replace deployment
error advice to mutate dependencies with maintainer-reviewed environment guidance.

LabJack: preserve startup cleanup and calibration; add body+close failure tests and
closed-use guards without output changes. Test native import isolation through factories.

SPAD: borrowed ownership, explicit reviewed pin policy and high/low transcript tests.
Do not introduce a false measured-state cache or disconnect the shared LabJack.

## Acceptance for every wrapper checkpoint

1. Success transcripts/API/import compatibility frozen and reviewed.
2. Focused whole-wrapper fake-transport tests, including primary+cleanup failure.
3. Relevant service/session/GUI tests and full offline suite; hardware tests stay excluded.
4. Changed-file Ruff format/check, compileall, CLI/native-import smoke, wheel build,
   TOML/local Markdown checks and diff whitespace review. No unsafe fixes.
5. Exact environment versions, skips, unavailable checks and physical requirements recorded.
6. Update architecture/roadmap/handover/hardware/deployment notes where semantics change.
7. Guarded installer against the current supplied snapshot; no Git or hardware mutation.
8. Maintainer-controlled physical acceptance before production use; no certification
   inferred from fakes. Retain the old release and rollback path.

## Merge and release position

Do not merge solely because the current 318-test headless suite is green. QtWidgets
acceptance is still open and several wrapper failure paths lack whole-module tests.
The deployment guide remains a proposed manual runbook, not an executed installer or
security boundary. Code permissions do not replace optical/electrical interlocks.

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
2026-10-29T08:46:24.4544246Z, HEAD `d2e29eb929567cdcc10bdf3fff907044c6815369`,
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
