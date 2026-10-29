# UC480 partial-start and cleanup checkpoint

Input `labtools_source_20261029_100151.txt`, HEAD `b4be98c4f619526a421af54f795365f14d95ac54`, branch `feature/shared-instrument-session`, upstream +4/-0. Tracked state recorded clean; seven unrelated installers are preserved.

The wrapper now tracks idle/setup/live acquisition state. If start fails after setup, it attempts the vendor stop operation and preserves the original BaseException plus cleanup details. Connect/exposure failure preserves the primary while closing a created camera. Close still attempts stop and camera-close independently and retains the established `UC480CameraError` caused by an `ExceptionGroup` for ordinary failures. Public camera/live state is cleared after close attempts, matching existing tests; teardown permanently blocks reconnect/commands because physical release may be uncertain. Context exit preserves a body exception if cleanup fails.

Preserved: lazy pyLabLib import, camera zero/backend selection, exposure seconds/readback, gain behaviour, frame wait/snap, horizontally mirrored owned C-contiguous arrays, buffer semantics and independent stop+close aggregation. No camera-selection, GUI, reconnect or other wrapper change.

Validation: 16 new whole-module fake-SDK tests; camera lifecycle plus inherited regressions 27 passed; full offline suite 420 passed, 5 skipped, 172 warnings. PyQt6 was absent, so Qt acceptance remains open. Ruff passed; compileall, CLI, TOML, native-free imports, wheel and Markdown/whitespace checks are part of local instructions. No physical camera/DLL was used.

Changed production: `src/labtools/devices/uc480_camera.py`. New test: `tests/test_uc480_lifecycle.py`. Relevant handover/roadmap/architecture/audit/plan/development/commands/hardware/deployment docs and this checkpoint are updated.

## Install and validate

```powershell
python .\apply_labtools_uc480.py --check
python .\apply_labtools_uc480.py --list
python .\apply_labtools_uc480.py --apply
$changedPaths = @(python .\apply_labtools_uc480.py --list)
$changedPython = @($changedPaths | Where-Object { $_ -like '*.py' })
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = 'offscreen'
$env:MPLBACKEND = 'Agg'
uv run --no-sync ruff format --check @changedPython
uv run --no-sync ruff check @changedPython
uv run --no-sync python -m pytest tests/test_uc480_lifecycle.py tests/test_reliability_regressions.py -q
uv run --no-sync python -m pytest -q -rs
git diff --check
git diff --stat
git status --short
```

Do not enable hardware tests. The installer verifies baselines with LF/CRLF/BOM tolerance, refuses new-file collisions and main/master/detached HEAD, creates an exact-byte external backup, writes atomically per file and restores ordinary partial failures. Rollback before later edits:

```powershell
python .\apply_labtools_uc480.py --rollback 'ACTUAL_BACKUP_DIRECTORY'
```

## Commit

```powershell
git add -- @changedPaths
git diff --cached --check
git diff --cached --stat
git diff --cached
git status --short
git commit `
  -m 'Harden UC480 partial acquisition startup and cleanup' `
  -m 'Track setup and live states, roll back failed starts through vendor stop, and preserve primary and cleanup failures.' `
  -m 'Retain frame ownership, mirroring, selection and stop-plus-close aggregation with whole-module fake-SDK coverage.'
```

Physical UC480 driver/DLL, camera selection, partial-start teardown and frame acceptance remain open. IDQ eval remains P0 and Qt remains gated. Next fixture-independent task: SC10 serial lifecycle/transcript coverage only, unless approved IDQ histogram fixtures arrive first.
