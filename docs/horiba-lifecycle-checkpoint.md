# HORIBA W2: startup and independent async cleanup

## Starting identity and scope

Input snapshot `labtools_source_20261029_084624.txt`, created
2026-10-29T08:46:24.4544246Z, HEAD `8293c1677d43e94fc9b50ede778cc5853dca5db7`,
branch `feature/shared-instrument-session`, upstream +2/-0. Index/tracked worktree are
recorded clean; five prior installers are untracked and preserved. Live Git is authoritative.

W2 changes HORIBA wrapper/backend lifecycle, adds one fake-SDK test module and updates
docs. No hardware, diagnostics, service launch, network endpoint, Git mutation, lab-PC
deployment, ACL/account, dependency or profile change occurred. No legacy runner or
HORIBA diagnostic script was executed. Acquisition gate remains open.

## Implementation

`HoribaSpectrometer.connect()` now owns DeviceManager construction/start, discovery,
mono/CCD open, configuration and identity verification in one BaseException cleanup
boundary. Duplicate connect is refused. Startup/body exception identity and traceback
remain primary when cleanup fails; cleanup is attached through notes and
`_horiba_cleanup_failures`, and `_labtools_cleanup_failed` is set.

`disconnect()` clears public handles, marks teardown permanent, and attempts CCD close,
the established one-second mono wait+close, and manager stop independently. Successful
stages are not repeated. Failed handles are retained privately as uncertain for explicit
disconnect-only retry. A stopped manager may invalidate retained device handles, so
retention is diagnostic ownership, not usability or recovery. Successful disconnect
is idempotent. Reconnect is refused after teardown; canonical configure subsequently
fails because public device handles are absent. No automatic reconnect/command retry.

Ordinary cleanup errors raise `ExceptionGroup`; cancellation/interrupt remains primary,
with other failures attached. The one-second wait is itself inside the mono cleanup
stage, so cancellation there does not prevent manager-stop attempt. Async context exit
preserves a body/cancellation error when disconnect also fails.

Both real backend context managers now catch disconnect `BaseException`, preserving an
existing operation/cancellation primary and marking cleanup failure. A standalone
disconnect failure remains visible. The real-worker regression uses the actual wrapper
with fake SDK handles and confirms cleanup failure faults the worker.

## Preserved contracts

No detector preset/identity, grating/mirror/ROI/slit command, unit, readback, exposure
setter/cache, polling/reset deadline, acquisition/dark/reduction ordering, shutter
behaviour, SDK close delay, persistent connection policy or data contract was changed.
Syncerity remains 0.065 s and Symphony 0.1 s; no 0.02 s override. W1 ITC policy,
IDQ eval parser, other wrappers, map schema/resume/determinism, profiles, recipes and
protected-core/writable-workspace boundaries are unchanged.

## Tests and validation

- Whole-module fake HORIBA SDK plus backend/worker module: **39 passed**.
- Focused wrapper/service/worker/alignment/import selection: **135 passed**.
- Full offline suite: **393 passed, 5 skipped, 172 warnings**.
- Five skips because PyQt6 is absent here: QtCore plus four QtWidgets modules. This is
  not Windows/Qt acceptance and does not unlock map allocation.
- Changed-file Ruff format/check: passed for two production files and one test file.
- Compileall, CLI help, TOML parsing, native-free simulation smoke and wheel build passed.
- Native-free smoke blocked HORIBA/PyVISA/u6/serial/pylablib/ZMQ imports, returned 64
  simulated samples and joined the worker.
- Python 3.12.15; temporary Ruff 0.17.3; pytest 9.1.1. Exact locked Windows environment
  was not reproduced. Warnings are inherited Matplotlib/pyparsing deprecations.
- An initial combined validation call exceeded the execution wrapper limit; focused and
  full suites were rerun separately to completion with the results above.

Fake tests stub SDK modules before importing the complete real wrapper. They cover
manager creation/start, mono/CCD open, configuration and detector identity, each cleanup
stage, combined errors, KeyboardInterrupt/CancelledError at startup/cleanup boundaries,
mono-delay cancellation, retry/idempotence, duplicate connect, context body cleanup,
loop/thread identity, success transcript and actual-wrapper worker faulting. No real SDK,
DLL, service or device discovery occurred. Physical SDK/shutter/optical acceptance remains.

## Exact changed files

Production:
- `src/labtools/devices/horiba_spectrometer.py`
- `src/labtools/runtime/spectrum_backend.py`

Tests:
- `tests/test_horiba_wrapper_lifecycle.py` (new)

Relevant documentation is updated, including handover, roadmap, architecture, audit,
repair plan, conventions, commands, hardware/deployment caveats and this checkpoint.
No dependency/vendor/profile/data file is changed or deleted.

## Install, check and rollback

Place `apply_labtools_horiba_w2.py` in the feature-branch root and close labtools tools.

```powershell
python .\apply_labtools_horiba_w2.py --check
python .\apply_labtools_horiba_w2.py --list
python .\apply_labtools_horiba_w2.py --apply
$changedPaths = @(python .\apply_labtools_horiba_w2.py --list)
$changedPython = @($changedPaths | Where-Object { $_ -like '*.py' })
git diff --check
git diff --stat
git status --short
git diff --cached --stat
```

The standard-library installer verifies affected current-snapshot contents with normal
LF/CRLF/BOM tolerance, refuses new-file collisions and main/master/detached HEAD, creates
an exact-byte external backup, writes per file atomically and restores originals after
ordinary partial failure. It does not claim multi-file power-loss atomicity. It uses only
read-only Git queries and performs no hardware/dependency/account action.

```powershell
python .\apply_labtools_horiba_w2.py --rollback 'ACTUAL_BACKUP_DIRECTORY'
```

Rollback refuses post-install edits. Keep installer/backup until acceptance.

## Local validation

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = 'offscreen'
$env:MPLBACKEND = 'Agg'
uv run --no-sync ruff format --check @changedPython
uv run --no-sync ruff check @changedPython
uv run --no-sync python -m pytest tests/test_horiba_wrapper_lifecycle.py -q
uv run --no-sync python -m pytest `
  tests/test_horiba_wrapper_lifecycle.py tests/test_spectrum_service.py `
  tests/test_spectrum_worker_phase4a.py tests/test_alignment_spectrum.py `
  tests/test_comparative_audit.py tests/test_project_structure.py -q
uv run --no-sync python -m pytest -q -rs
uv run --no-sync python -m compileall -q src tests examples
uv run --no-sync python -m labtools --help
uv build --wheel --out-dir "$env:TEMP\labtools-horiba-w2-build"
git diff --check
git diff --stat
git status --short
```

Do not enable hardware tests. Inspect Qt skip reasons; a zero exit code with skipped
QtWidgets is not acquisition acceptance. Remove offscreen settings before interactive use.

## Commit after review

No staging/commit was performed. Inspect the whole index first.

```powershell
git add -- @changedPaths
git diff --cached --check
git diff --cached --stat
git diff --cached
git status --short
git commit `
  -m 'Harden HORIBA partial startup and async cleanup ownership' `
  -m 'Clean partial SDK startup, attempt CCD, monochromator and manager teardown independently, and retain primary and cleanup failures.' `
  -m 'Prevent reconnect after teardown and expose real-wrapper cleanup failures to spectrum worker fault reporting.' `
  -m 'Add whole-module fake-SDK lifecycle coverage and update wrapper audit, roadmap, handover and release caveats.'
```

## Remaining acceptance and next bounded task

Windows/PyQt/HORIBA SDK and physical detector/shutter/optical acceptance remain required.
Native calls may block. The IDQ eval parser remains P0 without accepted fixtures. No
collision allocation or launcher change is included.

Next fixture-independent wrapper task: **W5 scanning-mirror/LJTick-DAC two-axis
preflight only**. Validate both finite requests and representable DAC codes before either
write, preserve calibration maths/byte encoding/order/pins, and report second-write
partial movement without automatic rollback/home. If representative IDQ histogram
fixtures arrive, prioritize isolated parser hardening instead. Do not combine wrappers.
