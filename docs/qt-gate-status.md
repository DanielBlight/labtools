# Qt acceptance gate: current checkpoint

## Input and decision

Input: `labtools_source_20261028_170656.txt`, HEAD
`a439207b4b6d6aec2fbf3575d2fa155893d318a3`, branch
`feature/shared-instrument-session`, upstream +2/-0. Two previous installers are
untracked; tracked worktree/index are recorded clean. No local Windows pass log was
attached. Test source, a commit message and bytecode do not establish executed passes.

The requested prerequisite is NOT met. No collision-allocation code or test changes
were made. This checkpoint adds [deployment guidance](lab-pc-deployment.md) and updates
current documentation. It is not a production deployment or an auto-updater.

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

## Documentation installer and commit

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
