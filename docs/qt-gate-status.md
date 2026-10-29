# Qt acceptance gate: current checkpoint

## Input and decision

Input: `labtools_source_20261028_215033.txt`, HEAD
`ceaabec9ea4882c1882f71facf604a04099a5992`, branch
`feature/shared-instrument-session`, upstream +0/-0. Three previous installers are
untracked; tracked worktree/index are recorded clean. No separate local Windows pass
log is embedded. Test source, a commit message and bytecode do not establish passes.

The prerequisite is NOT met. Gate rerun remains 15 passed / 4 skipped; no acquisition
changes were made. The additional [wrapper audit](device-wrapper-audit.md) is an
independent static/fake-method review, with [repair plan](device-wrapper-repair-plan.md).
It does not waive the Qt gate. This checkpoint updates docs only.

## Executed checks

Gate selection: alignment_window_acceptance, alignment_gui, spectrum_gui_phase1,
gui_lifecycle, qt_controllers and alignment_lifecycle_acceptance.

Result: **15 passed, 4 skipped**. QtCore and headless cases ran. All four QtWidgets
modules skipped because importing PyQt6.QtWidgets requires missing `libGL.so.1`.

Full offline suite: **318 passed, 4 skipped, 172 warnings**. The same four QtWidgets
modules skipped. Warnings are inherited Matplotlib/pyparsing deprecations.

Environment: Python 3.12.15; temporary PyQt6 6.11.0 and Ruff 0.17.3 outside the repo.
This is not the locked Windows environment. Lifecycle Python Ruff check and format
check passed. Compileall, CLI help, TOML parsing, wheel build and local Markdown target
checks passed. No hardware, diagnostic, discovery or physical endpoint was contacted.
No Git mutation or lab-PC installation/permission change was performed.

## Run locally before advancing

From the source checkout with its existing development environment:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = 'offscreen'
$env:MPLBACKEND = 'Agg'
uv run --no-sync python -m pytest `
  tests/test_alignment_window_acceptance.py `
  tests/test_alignment_gui.py `
  tests/test_spectrum_gui_phase1.py `
  tests/test_gui_lifecycle.py `
  tests/test_qt_controllers.py `
  tests/test_alignment_lifecycle_acceptance.py `
  -q -rs 2>&1 | Tee-Object .\qt-acceptance-output.txt
uv run --no-sync python -m pytest -q -rs
```

Inspect all skip reasons and failures. The QtWidgets modules must execute and pass;
a zero exit code with skipped modules is not acceptance. Preserve the full output
with the next snapshot. Do not enable --run-hardware. Remove QT_QPA_PLATFORM=offscreen
before interactive use. If failures occur, fix only lifecycle issues and stop there.

After this gate passes, implement collision-safe intensity-map directory allocation
in a separate bounded checkpoint, preserving first timestamp name, data, schema,
resume signatures, deterministic simulation and explicit backend selection. Use atomic
mkdir, retry only actual collisions, and add frozen-clock/concurrent/error tests.
Do not combine with launcher work, persistent HORIBA connections or io extraction.

## Historical deployment-documentation installer and commit

The supplied `apply_labtools_deployment_docs.py` updates docs only. It does not install
labtools on the lab PC or change accounts/ACLs. Run from the feature-branch repo root:

```powershell
python .\apply_labtools_deployment_docs.py --check
python .\apply_labtools_deployment_docs.py --list
python .\apply_labtools_deployment_docs.py --apply
$changedPaths = @(python .\apply_labtools_deployment_docs.py --list)
git diff --check
git diff --stat
git status --short
```

Retain its printed external exact-byte backup. Rollback refuses subsequent edits:

```powershell
python .\apply_labtools_deployment_docs.py --rollback 'ACTUAL_BACKUP_DIRECTORY'
```

After review, stage only this documentation checkpoint. Inspect unrelated staged files
before committing; git commit includes the whole index:

```powershell
git add -- @changedPaths
git diff --cached --check
git diff --cached --stat
git diff --cached
git status --short
git commit `
  -m 'Document protected lab-PC deployment and record Qt acceptance gate' `
  -m 'Add reviewed-wheel installation, standard operator access, separate recipes/data, offline updates and rollback guidance.' `
  -m 'Refresh current snapshot identity and validation evidence; keep collision-safe map allocation blocked pending executed QtWidgets acceptance.'
```

## Current wrapper-audit checkpoint

Use [current instructions](wrapper-audit-checkpoint.md), not the historical deployment
installer commands above, for this snapshot. The new installer changes docs only and
preserves all three untracked earlier installers. Run the local gate command above,
attach the complete output separately with the next snapshot, and inspect skip reasons.
No wrapper runtime repair or collision-allocation change is claimed here.
