# Alignment lifecycle hardening and acceptance

## Input and scope

Input snapshot: `labtools_source_20261028_155354.txt`, HEAD
`9f602792c048ef63b9598529637051ead04eccd2`, branch
`feature/shared-instrument-session`, upstream +1/-0. Only the previous audit installer
is recorded untracked. No Git mutation or physical hardware operation was performed.

This implements the next bounded roadmap checkpoint: alignment stop, busy, fault and
deferred-close hardening, with deterministic blocked-job regression coverage. It does
not implement a launcher, persistent HORIBA connections or another device workflow.

## Production changes

Only `src/labtools/gui/alignment_gui_horiba.py` changes:

- Start refuses an existing job even after Stop clears the repeat flag. This prevents
  a programmatic restart from losing the active handle before cleanup completes.
- Start refuses pending/accepted close and faulted/closing/closed workers.
- Start stays disabled after fault/close; the status explains application teardown.
- closeEvent alone shuts down a private worker after deferred cleanup, eliminating
  the duplicate close from _finish. Injected workers remain application-owned.
- Accepted close stops the completion-polling timer and prevents further submission.

Exposure floors remain Syncerity 0.065 s and Symphony 0.1 s. Detector options, commands,
QSettings, dark correction, immutable results, map schemas and standalone launch paths
are unchanged. Stop remains cooperative at the existing complete-operation boundary.

## Tests

`tests/test_alignment_lifecycle_acceptance.py` adds seven headless cases using the
real SpectrumService and SpectrumWorker with an injected fake backend. Independent
Events block capture and cleanup. Tests verify cancellation/busy ownership through
cleanup, restart, worker-loop/thread identity, and fault publication after connect,
configure, move, dark, capture and disconnect failures.

`tests/test_alignment_window_acceptance.py` adds twelve QtWidgets cases: stop/restart
handle retention, another client's busy owner, injected deferred close, six fault
stages, no modal after deferred close, private close exactly once on deferred close,
and UI-thread settings snapshot/immutable result plotting. Tests never connect to a
physical device. Fake backend gates are released in teardown.

## Validation and limits

- Focused backend/worker/audit/QtCore selection: 32 passed.
- Full offline suite: 318 passed, 4 skipped, 172 inherited warnings.
- Changed Python Ruff format/check: passed, Ruff 0.17.3.
- Compileall src/tests/examples, CLI help, TOML parsing and wheel build: passed.
- Relative Markdown target check: passed; external links/heading anchors not checked.
- QtCore controller tests: 8 passed.
- QtWidgets modules: skipped because libGL.so.1 is missing in this Linux environment.
  This includes the twelve new window cases, not twelve executed passes.

Python 3.12.15 with temporary PyQt6 6.11.0 and Ruff 0.17.3, outside the repository.
The exact uv.lock Windows environment was not reproduced. pyproject.toml and uv.lock
are unchanged. No hardware tests, diagnostics, discovery or physical endpoints ran.
Windows/QtWidgets acceptance and physical SDK/shutter behaviour remain unverified.
The phase is implemented but only partially accepted. Do not advance the launcher
based on skipped GUI tests.

## Install

Close GUIs and place `apply_labtools_alignment_lifecycle.py` in the repository root.
The installer targets the exact affected files from the input snapshot, refuses
main/master/detached HEAD and collisions, and preserves unrelated changes. It creates
an external exact-byte backup. Per-file writes are atomic; a normal partial failure
attempts restoration. Multi-file power-loss atomicity is not claimed.

```powershell
python .\apply_labtools_alignment_lifecycle.py --check
python .\apply_labtools_alignment_lifecycle.py --list
python .\apply_labtools_alignment_lifecycle.py --apply
$changedPython = @(python .\apply_labtools_alignment_lifecycle.py --list-python)
$changedPaths = @(python .\apply_labtools_alignment_lifecycle.py --list)
```

Keep the installer and printed backup path until acceptance. Do not rerun the previous
audit installer over these changes. No package installation or Git mutation is done.

## Check locally

Run each command and stop if it fails. Use the existing environment; do not enable
hardware tests. In particular, inspect skips: Windows Qt acceptance must execute.

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = "offscreen"
$env:MPLBACKEND = "Agg"
uv run --no-sync ruff format --check @changedPython
uv run --no-sync ruff check @changedPython
uv run --no-sync python -m pytest `
  tests/test_alignment_lifecycle_acceptance.py `
  tests/test_alignment_window_acceptance.py `
  tests/test_alignment_gui.py `
  tests/test_spectrum_gui_phase1.py `
  tests/test_gui_lifecycle.py `
  tests/test_qt_controllers.py `
  tests/test_spectrum_worker_phase4a.py `
  tests/test_comparative_audit.py `
  -q -rs
uv run --no-sync python -m pytest -q -rs
uv run --no-sync python -m compileall -q src tests examples
uv run --no-sync python -m labtools --help
uv build --wheel --out-dir "$env:TEMP\labtools-lifecycle-build"
git diff --check
git diff --stat
git status --short
git diff --cached --stat
```

If local Ruff requests formatting, format only changed files and rerun checks. Do not
use unsafe fixes. Rollback refuses post-install edits, including formatting. A build
may require cached build dependencies; report unavailable checks rather than silently
changing project metadata. Remove QT_QPA_PLATFORM=offscreen before interactive use.

## Rollback

Use the exact external backup path printed by --apply, before subsequent edits:

```powershell
python .\apply_labtools_alignment_lifecycle.py --rollback "ACTUAL_BACKUP_DIRECTORY"
```

## Commit after acceptance

Review existing staged changes first; git commit includes the whole index.

```powershell
git add -- @changedPaths
git diff --cached --check
git diff --cached --stat
git diff --cached
git status --short
git commit `
  -m "Harden alignment stop, fault and deferred-close lifecycle" `
  -m "Retain active job ownership through cancellation and cleanup; reject premature restart and closed-window submission." `
  -m "Disable restart after worker fault and give closeEvent sole private-worker shutdown ownership." `
  -m "Add deterministic blocked-backend and Qt window acceptance tests while preserving exposure minima and device semantics." `
  -m "Update architecture, roadmap, handover and validation guidance with explicit QtWidgets and hardware acceptance limits."
```

Do not stage either installer or source snapshots. Do not delete unrelated files.

## Next recommended changes

First execute the new QtWidgets tests on Windows and fix failures within this lifecycle
scope. Once that gate passes, implement collision-safe intensity-map output-directory
allocation in a separate checkpoint. Preserve the existing first timestamp name and
all output/resume contracts; add immediate-retry and concurrent-allocation tests.
Keep launcher Phase 7, persistent connection caching and device-wrapper reviews separate.

## Subsequent gate rerun on the 17:06 snapshot

The current input is HEAD `a439207b4b6d6aec2fbf3575d2fa155893d318a3`.
No local Windows pass log was attached. The gate rerun produced 15 passed / 4 skipped;
all QtWidgets modules remain blocked by missing libGL.so.1. Full suite remains
318 passed / 4 skipped. See [gate status](qt-gate-status.md). The map directory
collision fix has not advanced. Deployment guidance is now in the
[lab-PC runbook](lab-pc-deployment.md); it is proposed, not an executed installation.
