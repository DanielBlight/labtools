# Development handover: HORIBA lifecycle W2 and open Qt gate

## Expanded R1 requirements and supplied local evidence (2026-11-05)

The maintainer requires laser control, IDQ, mapping and annealing; the HORIBA-only
proposal and its 3-5 estimate are superseded. See the authoritative current section
of [release readiness](release-readiness.md). Feature requirements are not approval
of operating limits, optical path, concurrency or physical execution.

Actual supplied ITC logs/XML now establish 195 local targeted passes, zero failures/
errors/skips and a lint-pass artifact; all three hashes match the snapshot manifest.
Do not repeat unchanged ITC tests. Expanded offline/Qt/lint/build/staging evidence,
exact configuration/IDQ modes and physical/operator/deployment gates remain open.
Next is one guarded expanded offline evidence handoff, not another wrapper micro-fix.
ID900 histogram work stays deferred/P0 open; required IDQ counters are not silently
excluded or assumed to consume histogram data. Return instructions remain unchanged.
Historical narrower scope/estimates below are superseded, not approved.

## Current release planning authority (2026-11-05)

Use [R1 release readiness](release-readiness.md) as the single current scope/blocker
register. Proposed R1 is a controlled HORIBA-only spectroscopy pilot, awaiting
maintainer approval; it is not a blanket release of every tool. Current code is not
certified ready. The plan separates actual defects, missing evidence and optional
roadmap work. ID900 stays deferred with its return instructions unchanged.

Next task is R1 candidate evidence closure, not another automatic wrapper micro-fix.
Conditional estimate: 3-5 coherent checkpoints after consolidation, only under the
explicit assumptions in that register; not a guaranteed iteration count or date.
Historical gate records below retain their original scope. No production changes.

## Current setter-readback implementation (2026-11-05)

**Implemented, fake-transport validated; local lint/Windows acceptance not established.**
In set_current, immediately after get_current returns and before tolerance arithmetic,
nonfinite readback now raises RuntimeError with requested amperes and observed value.
The write has already occurred: this is verification failure, not pre-write rejection,
rollback, an interlock or proof of safe output. No new query/retry/close/output-off.

Authority: labtools_source_20261105_134133.txt, created UTC
2026-11-05T13:41:33.5423638Z, HEAD f3f230654859f54496da4178dc45c1611458f986,
branch feature/shared-instrument-session, upstream +7/-0, clean tracked worktree/index.
The readback-contract test differs from its old backup only by one removed blank line;
its AST is identical. Preserve that correction. Windows lint/test logs/XML are listed
but not exported; no pass or failure is inferred from commit, manifest or tool versions.

Fresh sandbox baseline: 178 passed. Final targeted run: 195 passed, comprising
55 readback cases, 96 finite-input cases and all 44 unchanged lifecycle cases;
zero failures/errors/skips, 39.69 seconds. Both affected test modules revise their
NaN/infinity expectations; 17 readback cases were added for exact diagnostics and
cleanup interruption. Existing finite tolerance, direct getter, conversion/query
exception identity and cleanup coverage are retained. Ruff attempt exited 1:
No module named ruff. Local lint is required; syntax/pytest are not lint acceptance.

Production change is only the setter readback guard; AST comparison after removing
that guard matches the entire baseline source. W1b input checks, finite tolerance
formula/strict comparison/mismatch text, command order and W1 cleanup are unchanged.
get_current and GUI second queries remain unchanged. No enable preflight, TEC delay,
timeout, mutation, temperature limit, fault state or automatic output-off policy.
ID900 remains deferred with its return instructions intact. No native VISA, hardware,
actual sleep, physical outputs, full-suite or Qt execution. No Git mutation.

### Next checkpoint: release scope and blocker consolidation

Stop automatically selecting another wrapper micro-task. The maintainer asks for
faster progress and a credible definition of ready. Next, inspect current source and
roadmap once, propose a named first-release workflow scope, and consolidate a finite
release-blocker/evidence matrix. Distinguish demonstrated defects, unresolved design
questions, missing evidence and optional roadmap work. Do not treat all planned
phases as mandatory for a narrower release, or waive required physical acceptance.
Do not count historical Qt sandbox failures as current failures after recorded
Windows passes; preserve current evidence gaps separately.

Prefer one checkpoint per coherent blocker batch with implementation/tests/docs
and one local validation handoff, not automatic contract/implementation pairs for
already-decided changes. Batch only independent compatible changes with explicit
acceptance; preserve separate safety decisions and user approval for hardware.
A proposed three-stage path (scope/blockers, bounded blocker batch if needed,
release acceptance/deployment) is a planning structure, NOT an estimate that three
iterations will suffice. No defensible project-wide count or date is established.
No new architecture, launcher, wrapper, GUI or release-policy change is authorized
by this scheduling note. ID900 is not automatically reopened.

Historical sections below retain earlier evidence; this section supersedes their
readback-unimplemented statements and next-microtask pointers only.

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

## Owner-label contract decision checkpoint (2026-11-05)

This later checkpoint characterizes owner labels; it does not reopen or replace
v4's recorded Windows acceptance. See [owner-label decision](hyperspectral-owner-contract.md).
Decision: reservation labels remain provider/runtime-owned diagnostics. The
validated, recipe-serialized request label does not automatically override a
provider. No owner propagation or production behavior change is implemented.

Authority: `labtools_source_20261105_111524.txt`, HEAD
`1bdef873daaa94e84e0455eb1e80b73d9a330a77`, branch
`feature/shared-instrument-session`, clean tracked worktree/index, upstream +1/-0.
The actual v4 evidence-command output and raw logs/XML remain absent from this
export; local raw-artifact verification is not claimed.

Validation: 60 targeted offline cases passed (26 new characterization cases),
zero failures/errors/skips. Ruff could not execute: the sandbox has no `ruff`
module. Local lint remains required; no dependencies were installed. Production
source, existing tests, runner, schemas, limits and backend selection are unchanged.
The v4 sections below are historical closure records, including their old next-step
instructions; this section supersedes only their deferred owner-label question.

## Current closure checkpoint v4: recorded Windows acceptance (2026-11-05)

**The remaining widget and full-offline gates passed in the supplied Windows run.**
This supersedes the open-gate status in the historical v3/recovery sections below;
it does not convert those earlier sandbox failures into passes.

Authoritative snapshot: `labtools_source_20261105_074708.txt`, created UTC
2026-11-05T07:47:08.2392102Z. HEAD
`0ce76d7ce8c81ab01ab9d61daddc39a606c77185`, branch
`feature/shared-instrument-session`, upstream +2/-0. No tracked/staged changes are
recorded. Preserve the untracked v2/v3 backups, v3 installer, validation directory
and measurement-data.

Evidence: `.labtools-validation/source-audit-20261105T074324574893Z/results.json`.
The runner requested `all`; lint and both prerequisites passed; core **68 passed**,
widgets **12 passed**, full offline **608 passed**. Each test gate records zero
failures/errors/skips; every process returned 0 with `timed_out: false`.
`all_gates_passed` and `requested_gates_passed` are true. Counts overlap and must
not be summed. The full gate used `-m "not hardware"`; deselection totals are not
recorded in the JSON and are not inferred to be zero.

All seven recorded source SHA-256 values match the exported current files exactly
as UTF-8/LF bytes, including the runner. All nine v3 delivered files match the
embedded v3 backup's installed text. This establishes evidence-to-source linkage,
not a new test execution in this assistant environment.

The raw logs/XML are listed with hashes/sizes but their contents are NOT included
as snapshot file sections. Their counts are available through the runner's JSON;
independent raw-log/XML review was not performed here. The standalone v4 installer
provides a read-only `evidence` command to verify those exact artifacts locally,
compare XML counts and confirm the seven source hashes. Do not invent absent log
contents or treat a missing artifact as success.

This checkpoint changes documentation only. Production code, tests, validation
runner, plotting/click selection, raw-sum/mask semantics, immutable results,
archive/schema versions, limits, dependencies and hardware commands are unchanged.
No additional application correction was justified. The widget gate exercised
cached-dark transitions and delayed-cleanup close/restart refusal; the core gate
includes repeated terminal failures, immediate cancellation, borrowed ownership
and the four unchanged import-isolation tests.

The bounded offline recovery acceptance is closed for this recorded Windows run.
Hardware/native-SDK physical acceptance, visible operator acceptance beyond these
automated tests, request.owner/provider-label review and the original pre-audit
comparison remain outside this closure. The original earlier comparison inputs
were not supplied; no missing requirements are invented. Do not begin a new
feature/architecture phase as part of this checkpoint.

### Next bounded continuation

Verify the original ten evidence artifacts locally with the v4 `evidence` command,
retain the results/logs/XML and commit only the six documentation paths after
review. If artifact hashes/XML disagree, reopen evidence reconciliation only.
Do not rerun old v2/v3 rollback against this later documentation state. The v4
backup is separate and exact-byte rollback refuses later edits.

---

## Historical checkpoint record (not current gate status)

## Current validation checkpoint v3 (2026-11-02)

Authoritative input: `labtools_source_20261102_121604.txt`, HEAD
`b23c6fd95e0c0027c924f2d1e1f37e76fc5f4cf5`, branch
`feature/shared-instrument-session`, upstream +1/-0; no tracked changes recorded.
Eight v2 recovery files match exactly; two have comment-only, AST-equivalent
changes. Preserve this baseline rather than reverting those edits.

Sandbox core gate: **68 passed, no skips or deselections**, including all four
unchanged import-isolation tests and seven QtCore lifecycle cases. No application
source changes are made by v3. Widget acceptance remains blocked by missing
`libGL.so.1`; the full offline attempt timed out without completion. No lab-PC
acceptance log was supplied. Hardware and the original older-snapshot audit remain
unverified. The earlier recovery sections below are historical evidence.

See [source-audit-validation.md](source-audit-validation.md) for the exact scope,
commands, evidence and remaining gates. Run
`uv run --no-sync python scripts/validate_source_audit.py --gate all` locally and
retain its logs/XML/results.json. Core-only success is not full acceptance.

## Source-audit recovery checkpoint (2026-11-02)

Baseline: `labtools_source_20261102_114759.txt`, HEAD
`cefe007f309bd5389ca7782bce9b9e813c66257e`, branch
`feature/shared-instrument-session`. This checkpoint is a bounded current-source
review, not a verified comparison with the earlier snapshot or earlier installer.
See [source-comparison-audit.md](source-comparison-audit.md) for findings, evidence,
validation limits and remaining work. Earlier checkpoint descriptions below are
historical and do not establish current validation status.

Owned hyperspectral runtime validation is now inside cleanup protection; cleanup
failure is attached to an active primary exception instead of replacing it.
Borrowed runtimes remain caller-owned. The Qt worker reports cancellation and
process-control exceptions through its terminal failure signal. Cached GUI dark
records are passed only in `pre_taken` mode. Existing plotting, nearest-pixel
selection, raw-sum semantics, schemas and physical settings are unchanged.

Validation: 53 targeted tests passed, one Qt module skipped, four subprocess-import
tests deselected after baseline timeouts. Full-suite completion, Qt acceptance,
Ruff and hardware acceptance remain unverified in this environment.

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


## Hyperspectral simulation GUI plotting checkpoint

The public scripted hyperspectral measurement remains frozen and Qt-free. The operator GUI remains simulation-only and presents a synthetic NaN-safe raw spectral sum, completion mask, click-selected completed pixel, and an immutable selected spectrum in wavelength nanometres against mirror voltages. Typed progress intentionally contains no partial arrays, so live spectral/map plotting is not implemented. GUI resume, multi-recipe pipelines, anneal dispatch, and real-hardware execution remain unsupported. The legacy runner is not the GUI backend. `--confirm-real` applies only to guarded scripted execution and is not a GUI safety control. HORIBA exclusion remains process-local. Offline Qt tests and synthetic plots are not physical, calibration, timing, optical, Windows-native SDK, or Qt-production acceptance.


## Expanded R1 tooling follow-up, 5 November 2026

The complete expanded-R1 lint inventory contains 44 findings in ten test/support
files. The bounded follow-up changes only those files and this documentation.
No production hardware behavior, acquisition feature, dependency metadata,
backend selection, IDQ counting scope or ID900 histogram deferral is changed.

Original evidence remains historical: accepted ITC 195 cases and remaining
offline 590 cases. Do not add affected reruns to these counts. Source linkage
matched all 143 recorded fingerprints before correction. The original failed
results must remain immutable.

The conftest change is global collection support, not a local test-only impact.
Fifty fake-object hook comparisons preserve marker/permission behavior. Full
590-node and 195-node collection comparison on the original Windows environment
is still required. If either differs, stop reuse and assess broader regressions.
The bounded execution scope is eight edited test modules, 175 cases, plus those
collection checks. Unchanged 415 remaining-offline cases and accepted ITC 195
may be reused only with valid source and collection linkage.

Development validation: 170 non-Qt affected cases passed; a final 69-case rerun
covered subsequent context-header simplification. Five GUI subprocess cases,
full Windows collection and Ruff remain pending. No skipped GUI test is accepted.

Packaging is blocked by unavailable approved build-only backend material.
pyproject.toml already declares setuptools>=69. Do not add duplicate metadata,
change backend, install into acquisition .venv, or choose an unreviewed version.
Supply an approved exact setuptools wheel/version/SHA-256/provenance and all
required hash-pinned build-only wheels. The follow-up runner creates a separate
build-only environment and records versions, commands and resulting wheel hash.
Staging uses a non-editable wheel with explicitly inherited dependency paths;
this is not clean-room dependency, native-SDK, physical, operator or deployment
acceptance. No wheel or staging pass is claimed at this checkpoint.

Next coherent task: run the linked tooling/collection gate on the established
Windows environment, then close only the approved-backend wheel/staging gap.
Do not start another wrapper or acquisition feature task.


### Reconciled tooling delivery v2 (2026-11-05)

The tooling package was rebased onto the current expanded-R1 documentation,
retaining every existing line and the original ten test/support corrections.
The original parent results and its artifact hashes remain authoritative and
immutable. The original 143 source fingerprints are unchanged.
The follow-up section above records historical delivery evidence, not a new
Windows or Qt run. Windows collection/lint/175-case verification remains pending.
The linked runner checks the reconciled documentation as well as source files;
no source-linkage guard is waived. Run verification before committing.
Earlier instructions to rerun the original expanded evidence handoff are
superseded for this checkpoint by the linked tooling follow-up only.
No production code, dependencies, device behavior or ID900 deferral is changed.
Cleanup and archived-backup restoration remain separate from this checkpoint.
Build/staging remains blocked pending reviewed build-only prerequisites.

## Packaging and staged-wheel simulation checkpoint (2026-11-09)

At source HEAD `6074fdad670ed0099c44bbab44c5049aee537c9a`, a clean Git
archive was built outside the repository with `setuptools 84.2.1` in a separate
build environment. The result was `lab_tools-0.1.0-py3-none-any.whl`. The wheel
was installed non-editably into a separate staging environment, and core
`labtools`, `labtools.measurements`, and `labtools.processing.spectrum` imports
resolved from that staged installation.

The staged wheel then completed the existing deterministic intensity-map
simulation with `--points 5 --seed 12345`: all 25 synthetic points completed and
the output was explicitly labelled `SYNTHETIC DATA ONLY`. Output, build and
staging artifacts remained outside the repository. No hardware was accessed and
the acquisition `.venv` was not modified.

Third-party dependencies were inherited read-only from the acquisition `.venv`.
This closes the immediate wheel-build, staged-install, staged-import and synthetic
smoke-test gap only. It is not clean-room dependency, native-SDK, permissions,
operator, physical-hardware, rollback, lab-PC deployment or release acceptance.

## Collision-safe intensity-map output allocation (2026-11-09)

New intensity-map runs now allocate their timestamp directory atomically. If a run
already owns the same second-resolution name, later runs retain the historical base
name format and use deterministic `-001`, `-002`, and subsequent suffixes instead of
failing or reusing an existing directory. Resume continues to use its explicitly
selected directory; file schemas, measurement facades, hardware behaviour and backend
selection are unchanged. This is an offline filesystem reliability correction, not
physical, native-driver, operator or deployment acceptance.

## Collision-safe laser-anneal output allocation (2026-11-09)

New logged anneal runs now allocate their timestamp directory atomically. If a run
already owns the same second-resolution name, later runs retain the historical base
name format and use deterministic `-001`, `-002`, and subsequent suffixes rather than
failing or reusing an existing directory. Run-log schemas, scan ordering, shutter,
mirror, rotation-stage and cancellation behaviour are unchanged. This is an offline
filesystem reliability correction, not optical-path, physical-safety, native-driver,
operator or deployment acceptance.

## Laser-anneal cancellation cleanup characterization (2026-11-09)

An offline fake-device test now characterizes cancellation during the first point
dwell. It verifies that the shutter command sequence is closed, open, closed; the
result is stopped and incomplete with no completed point; and the mirror is returned
to its configured home coordinates. No production code or hardware behaviour changed.
This establishes the ordinary cancellation path only; injected cleanup failures,
rotation-stage return, native drivers, optical-path safety and operator acceptance
remain separate gates.

