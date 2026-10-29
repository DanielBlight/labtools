# ITC4000 W1: transport lifecycle checkpoint

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
