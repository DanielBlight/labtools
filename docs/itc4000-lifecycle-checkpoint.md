# ITC4000 W1: transport lifecycle checkpoint

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

## Input and scope

Input: `labtools_source_20261029_075745.txt`, created
2026-10-29T07:57:45.1279373Z, HEAD `ad2a95b9813bc8407d54120a3997571c24d52450`,
branch `feature/shared-instrument-session`, upstream +1/-0. Tracked worktree/index
recorded clean. Four untracked earlier installers are preserved: alignment-lifecycle,
comparative-audit, deployment-docs and wrapper-audit. No separate local Qt pass output
is embedded. A text export does not provide the live .git index or checkout state.

This implements W1 only. No staging, commit, merge, push, reset, branch switch,
hardware test/diagnostic/discovery, vendor service launch, physical endpoint,
lab-PC deployment, account or ACL operation was performed. No other wrapper or
acquisition behaviour changed. All local tests use fake handles or explicit simulation.

## Findings and implementation

The prior constructor leaked a ResourceManager if open_resource failed, and both
handles if termination setup or initial *CLS failed. close used try/finally so a
manager-close failure replaced an instrument-close failure. Context exit could mask
a body exception. Whole-module fake-PyVISA tests now cover these paths.

### Ownership and failure contract

- Initialize handle ownership before acquiring the manager/instrument.
- Cover manager creation, resource open, termination setup and initial *CLS in a
  startup boundary that catches BaseException solely to clean up and re-raise.
- Attempt instrument close then manager close independently, even after interruption.
- Ordinary cleanup failures raise ExceptionGroup retaining each original exception.
- KeyboardInterrupt/CancelledError remains the primary BaseException, not an ordinary
  ExceptionGroup member. Other failures are retained structurally on the primary in
  _itc4000_cleanup_failures and described in notes.
- Startup/body exceptions remain primary if cleanup also fails. A clean body receives
  the cleanup failure. Successful context exit and close remain ordinary None returns.
- Once teardown starts, _ensure_open refuses all commands/queries. _closed becomes
  true only when both handles have been released successfully or were never acquired.
- Clear successful handles, retain failed handles as uncertain. A later explicit close
  retries only retained stages. There is no automatic retry/reconnect or command retry.
- A manager close can invalidate an instrument whose close failed. Retained references
  do not establish a usable connection or guarantee that retry can recover it. If a
  constructor fails, no wrapper is returned; exception/traceback and cleanup details
  are retained for maintainer investigation, not automatic resurrection.

### Compatibility preserved

Public import/class/constructor, one VISA session, address/default limits, current in
amperes, timeout, termination values, initial *CLS, SCPI strings/order, *OPC?/error/
readback sequence and TEC policy are unchanged. AST comparison confirms every existing
command/setter method is unchanged. Only __init__, _ensure_open, close and __exit__
change, with one private cleanup-detail helper added.

No laser-off, TEC-off, current reset, shutter or motion command was added to close.
Transport release is not a physical safe-state policy. Ordinary close failure type
is deliberately now ExceptionGroup; existing broad Exception handlers still catch it,
but callers catching only a specific driver exception may need to inspect the group.
Startup/body primary exception identity is preserved. Failed-close command refusal is
intentional. Native calls may still block; no hard shutdown deadline is claimed.

Finite-input policy is not changed: the audited NaN constructor gap remains W1b.
IDQ get_histogram eval(raw) remains P0 and unfixed, requiring representative accepted
response fixtures and bounded grammar in a separate checkpoint. No firmware syntax
was invented. HORIBA/SC10/DLT/camera/DAC/Kinesis/LabJack/SPAD findings remain planned.

Syncerity 0.065 s and Symphony 0.1 s, map schema/resume/deterministic model, profiles,
recipes and protected-core/writable-workspace deployment boundary remain unchanged.
No collision-safe map allocation or launcher was implemented; Qt acquisition gate stays open.

## Consumers reviewed (not executed against hardware)

- runtime/lazy_devices.py: lazy factory returns the real wrapper; no cache/owner added.
- runtime/map_devices.py and acquisition/intensity_map.py: composed laser factory,
  existing broad cleanup boundaries; no consumer code changed.
- gui/intensity_map_gui.py and gui/spectrum_gui_horiba.py: optional laser factory,
  existing broad exception handlers; actual QtWidgets execution remains unavailable.
- acquisition/run_hyperspectral_scan.py: legacy direct constructor/control/cleanup;
  inspected as source only, never executed.
- simulation/map_backend.py and existing project-structure/cleanup tests: fake seams
  remain separate from native transport and are not physical acceptance.

External/private scripts are unknown. No public API was retired. A consumer that drops
a failed wrapper reference may still require maintainer teardown; this checkpoint does
not rewrite consumer ownership or guarantee recovery after driver failure.

## Validation

- Baseline full rerun: **318 passed, 4 skipped, 172 warnings**.
- New whole-module fake-PyVISA lifecycle module: **44 passed**.
- Focused ITC/service/import selection: **179 passed**.
- Final full offline suite: **362 passed, 4 skipped, 172 warnings**.
- Same four QtWidgets modules skip: alignment GUI, alignment window acceptance,
  spectrum GUI Phase 1 and GUI lifecycle, because libGL.so.1 is missing.
- Changed-file Ruff format/check: **passed**, two Python files formatted.
- Guarded installer: dry-run, LF/CRLF matching, baseline/new-file refusal, apply,
  exact-byte rollback, post-edit refusal, partial-failure restoration and protected/
  detached-HEAD refusal passed in a temporary copy with read-only Git responses mocked.
  No Git mutation was used for installer validation.
- Compileall src/tests/examples and CLI help: **passed**.
- TOML parsing: **passed**, pyproject.toml/uv.lock unchanged.
- Native-free import/simulation smoke: **64 samples**, worker joined; PyVISA/u6/serial/
  pylablib/HORIBA/ZMQ imports blocked during smoke. Lazy factory import stays native-free.
- Wheel build: **lab_tools-0.1.0-py3-none-any.whl** built using installed setuptools.
  Existing build warning: packaging is old for license-expression validation.
- Relative Markdown targets: 141 checked, none missing. Source/docs/test whitespace
  review passed after final edits. External URLs, heading anchors and the live Git
  index are not checked here.

The 44 tests load the complete real wrapper module in an isolated module namespace
with monkeypatched fake pyvisa and pyvisa.resources modules. They are not AST method
extraction. Tests cover every startup stage with OSError, KeyboardInterrupt and
CancelledError; individual/combined close failures; startup/body plus cleanup failures;
explicit retry/idempotence/closed use; success transcript/defaults and caller thread ID.
No real ResourceManager or vendor DLL/device discovery occurs. This is not a real
PyVISA backend, Windows QtWidgets or physical instrument acceptance.

Environment: Python 3.12.15, temporary Ruff 0.17.3 and PyQt6 6.11.0 outside the repo,
pytest 9.1.1, preinstalled scientific dependencies. The exact uv.lock Windows environment
was not reproduced. Warnings are inherited Matplotlib/pyparsing deprecations. No
--run-hardware flag was used. An initial combined validation shell hit its time limit;
the full suite was rerun separately to completion with the final result above.

## Install/check/rollback

Place `apply_labtools_itc4000_w1.py` in the current feature-branch repository root.
Close all GUIs/acquisitions first. This updates source/tests/docs only; it does not
install the application on the lab PC, change dependencies or contact devices.

```powershell
python .\apply_labtools_itc4000_w1.py --check
python .\apply_labtools_itc4000_w1.py --list
python .\apply_labtools_itc4000_w1.py --apply
$changedPaths = @(python .\apply_labtools_itc4000_w1.py --list)
$changedPython = @($changedPaths | Where-Object { $_ -like '*.py' })
git diff --check
git diff --stat
git status --short
git diff --cached --stat
```

Stop on a mismatch. The installer checks affected current-snapshot files with LF/CRLF
and BOM tolerance, refuses new-file collisions and main/master/detached HEAD, stores
exact original bytes outside the repo, writes per-file atomically and restores originals
on ordinary partial failure. It does not claim multi-file power-loss atomicity. Only
read-only Git queries are used; no Git mutation, dependency install or hardware action.
Keep the printed backup and installer. Do not rerun older migration installers.

```powershell
python .\apply_labtools_itc4000_w1.py --rollback 'ACTUAL_BACKUP_DIRECTORY'
```

Rollback restores exact bytes and refuses post-install edits, including formatting.

## Local validation commands

Run each command separately; stop on failures. Do not enable hardware tests.

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = 'offscreen'
$env:MPLBACKEND = 'Agg'
uv run --no-sync ruff format --check @changedPython
uv run --no-sync ruff check @changedPython
uv run --no-sync python -m pytest tests/test_itc4000_lifecycle.py -q
uv run --no-sync python -m pytest `
  tests/test_itc4000_lifecycle.py tests/test_project_structure.py `
  tests/test_cleanup_failures.py tests/test_spectrum_service.py `
  tests/test_shared_map_backend.py tests/test_comparative_audit.py -q
uv run --no-sync python -m pytest -q -rs
uv run --no-sync python -m compileall -q src tests examples
uv run --no-sync python -m labtools --help
uv build --wheel --out-dir "$env:TEMP\labtools-itc-w1-build"
git diff --check
git diff --stat
git status --short
```

Inspect Qt skip reasons: zero exit code with skipped QtWidgets is not acquisition
acceptance. Capture the complete local Qt gate output using docs/qt-gate-status.md
before advancing map allocation. Remove QT_QPA_PLATFORM=offscreen before interactive
use. Do not mutate dependencies/lockfiles merely to make an unavailable check pass.

## Commit after review

The following are maintainer commands only; no staging/commit was performed here.
Inspect unrelated staged files first because git commit includes the whole index.

```powershell
git add -- @changedPaths
git diff --cached --check
git diff --cached --stat
git diff --cached
git status --short
git commit `
  -m 'Harden ITC4000 transport startup and teardown ownership' `
  -m 'Clean partial startup handles, attempt independent close stages and retain primary and cleanup failures.' `
  -m 'Block commands after teardown starts and retain uncertain handles for explicit close-only retry without new output commands.' `
  -m 'Add whole-module fake-PyVISA lifecycle coverage and update wrapper audit, roadmap, handover and release caveats.'
```

## Remaining acceptance and next bounded task

Maintainer-controlled Windows/PyVISA/driver and real-device transport acceptance remain
required before deployment. Review output/TEC policy and failure recovery without
assuming transport close disables emission. No physical validation was performed.
QtWidgets, other wrappers, IDQ parser and map-directory collision remain open.

Next fixture-independent wrapper task: **W2 HORIBA partial startup and independent
async cleanup only**. Preserve optical commands/delays, detector identity, minima and
loop ownership; add whole-module fake SDK failure/cancellation tests. No timeout policy,
exposure setter change, persistent connections, GUI redesign or other wrapper in W2.
If accepted IDQ histogram response fixtures become available, prioritize the isolated
P0 parser checkpoint instead. Acquisition lane remains Qt gate then collision allocation.

## Exact changed-file inventory

- `docs/README.md` (modified)
- `docs/ai-handover.md` (modified)
- `docs/architecture.md` (modified)
- `docs/commands.md` (modified)
- `docs/development-conventions.md` (modified)
- `docs/development.md` (modified)
- `docs/device-wrapper-audit.md` (modified)
- `docs/device-wrapper-repair-plan.md` (modified)
- `docs/hardware/spectroscopy.md` (modified)
- `docs/itc4000-lifecycle-checkpoint.md` (new)
- `docs/lab-pc-deployment.md` (modified)
- `docs/qt-gate-status.md` (modified)
- `docs/refactor-roadmap.md` (modified)
- `docs/wrapper-audit-checkpoint.md` (modified)
- `src/labtools/devices/itc4000.py` (modified)
- `tests/test_itc4000_lifecycle.py` (new)

No files are deleted. Only one production wrapper changes; all other runtime,
acquisition, simulation, profiles, vendor files and dependency metadata remain unchanged.

## Subsequent W2 status

HORIBA W2 is now implemented at input HEAD `8293c1677d43e94fc9b50ede778cc5853dca5db7`.
ITC W1 behaviour is unchanged. See [W2 checkpoint](horiba-lifecycle-checkpoint.md).
IDQ P0 and ITC W1b remain open; acquisition gate remains unmet.
