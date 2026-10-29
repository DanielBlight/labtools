# Wrapper-audit checkpoint: installation, validation and continuation

## Result and scope

The supplied source snapshot is `labtools_source_20261028_215033.txt`, HEAD
`ceaabec9ea4882c1882f71facf604a04099a5992`, branch
`feature/shared-instrument-session`, upstream +0/-0. Tracked worktree/index are recorded
clean; three previous installers are untracked. Live Git state is not accessible from
a text export. No Git mutation, hardware operation, diagnostic, discovery, account/ACL
change or lab-PC deployment was performed.

**Acquisition gate remains blocked.** No separate complete local Qt pass output is
embedded. The gate rerun is 15 passed / 4 skipped; all four QtWidgets modules skip
because libGL.so.1 is missing. No collision-allocation or wrapper runtime changes were
made. The additional wrapper request is satisfied by an independent evidence audit and
staged repair plan, not an untested broad rewrite.

Read [audit](device-wrapper-audit.md) and [repair plan](device-wrapper-repair-plan.md).
Most wrappers benefit from narrow lifecycle/validation fixes. IDQ/DLT needs staged
internal ownership decomposition behind its existing facade. No new universal device
framework is justified. The audit records a P0 histogram response-eval finding and
P1 ITC/HORIBA/DAC/camera failure-path findings, with evidence and uncertainty separated.

## Validation evidence

- Qt gate: **15 passed, 4 skipped**. QtCore/headless cases execute; QtWidgets does not.
- Full offline suite: **318 passed, 4 skipped, 172 warnings**.
- Eight extracted-method fake-handle probes confirmed ITC startup/teardown/NaN,
  HORIBA startup/close, DAC partial-write and camera partial-start observations.
  These are not eight new pytest tests or hardware acceptance.
- Device Ruff check: **passed**. Format check: **12 files already formatted**.
- Installer tests: dry-run, LF/CRLF matching, baseline/new-file refusal, apply, exact-byte
  rollback, post-edit refusal, partial-write recovery and main/master/detached refusal
  passed in a temporary copy with read-only Git responses mocked. No Git mutation.
- Compileall src/tests/examples: **passed**.
- CLI help: **passed**.
- pyproject.toml and uv.lock parse: **passed**, files unchanged.
- Native-free simulated alignment smoke: **64 samples**, worker joined; transport/SDK
  imports blocked during this smoke.
- Wheel: **lab_tools-0.1.0-py3-none-any.whl built** with installed setuptools backend.
  Build warned that installed packaging is old for license-expression validation.
- Relative Markdown targets: 129 checked, none missing. No-index whitespace check:
  passed against reconstructed input docs. External URLs/heading anchors and the live
  Git index are not validated here.

Environment: Python 3.12.15, temporary PyQt6 6.11.0 and Ruff 0.17.3, preinstalled
scientific dependencies. This is not a reproduced locked Windows environment.
Warnings are inherited Matplotlib/pyparsing deprecations. Hardware modules remain
excluded by the existing opt-in guard; --run-hardware was not enabled.

## Exact checkpoint inventory

All changes are under docs/. No production/test Python, pyproject.toml, uv.lock,
profiles, recipes, data or vendor files change. Existing files modified:

- docs/README.md
- docs/ai-handover.md
- docs/alignment-lifecycle-acceptance.md
- docs/architecture.md
- docs/commands.md
- docs/development-conventions.md
- docs/development.md
- docs/hardware/spectroscopy.md
- docs/intensity-map-simulation.md
- docs/lab-pc-deployment.md
- docs/qt-gate-status.md
- docs/refactor-roadmap.md

New files:

- docs/device-wrapper-audit.md
- docs/device-wrapper-repair-plan.md
- docs/wrapper-audit-checkpoint.md

Expected worktree after apply: these 12 modifications and three new docs, unstaged,
plus the user's existing untracked files and any other live unrelated changes. No
files are deleted. The audit includes a method index and first-party import inventory.

## Install this documentation checkpoint

Place `apply_labtools_wrapper_audit.py` in the feature-branch repository root. This is
NOT a lab-PC application installer and does not repair runtime wrappers.

```powershell
python .\apply_labtools_wrapper_audit.py --check
python .\apply_labtools_wrapper_audit.py --list
python .\apply_labtools_wrapper_audit.py --apply
$changedPaths = @(python .\apply_labtools_wrapper_audit.py --list)
git diff --check
git diff --stat
git status --short
git diff --cached --stat
```

Stop on a mismatch. The installer verifies affected current-snapshot files, tolerates
normal line endings, refuses new-file collisions and main/master/detached HEAD,
backs up exact original bytes outside the repository and writes each file atomically.
It restores originals after an ordinary partial failure. It does not claim multi-file
power-loss atomicity. It performs only read-only Git queries, no staging/history/branch
mutation, dependency installation, account/ACL changes or hardware actions.

Keep the printed backup and installer until review. Do not rerun earlier migration
installers against this checkpoint. Do not delete unrelated untracked installers.

### Rollback

Use the actual printed external backup directory, before subsequent edits:

```powershell
python .\apply_labtools_wrapper_audit.py --rollback 'ACTUAL_BACKUP_DIRECTORY'
```

Rollback restores exact original bytes and refuses to overwrite post-install edits.

## Capture the missing local Qt evidence

Run on the actual Windows development checkout using its existing environment, not
against physical devices. Logs go outside the repository so they are not accidentally
staged. Run each command separately and inspect failures/skips.

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = 'offscreen'
$env:MPLBACKEND = 'Agg'
$Evidence = Join-Path $env:TEMP ('labtools-qt-' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Evidence -Force | Out-Null
uv run --no-sync python -m pytest `
  tests/test_alignment_window_acceptance.py `
  tests/test_alignment_gui.py `
  tests/test_spectrum_gui_phase1.py `
  tests/test_gui_lifecycle.py `
  tests/test_qt_controllers.py `
  tests/test_alignment_lifecycle_acceptance.py `
  --junitxml "$Evidence\qt-acceptance.xml" `
  -q -rs 2>&1 | Tee-Object "$Evidence\qt-acceptance-output.txt"
$GateExit = $LASTEXITCODE
Write-Host "Qt gate exit code: $GateExit"
Write-Host "Evidence directory: $Evidence"
```

A zero exit code with skipped QtWidgets modules does not pass the gate. Attach the
complete text log separately with the next snapshot (and XML if supported). If a
lifecycle case fails, fix only lifecycle failures and stop at that checkpoint. Remove
QT_QPA_PLATFORM=offscreen before interactive GUI use. Do not enable hardware tests.

### Remaining checks

No Python changed here; the device lint checks are read-only audit evidence.

```powershell
uv run --no-sync ruff format --check src/labtools/devices
uv run --no-sync ruff check src/labtools/devices
uv run --no-sync python -m pytest -q -rs
uv run --no-sync python -m compileall -q src tests examples
uv run --no-sync python -m labtools --help
uv run --no-sync python -c "import tomllib; from pathlib import Path; [tomllib.loads(Path(p).read_text(encoding='utf-8')) for p in ('pyproject.toml','uv.lock')]; print('TOML parsed')"
uv build --wheel --out-dir "$env:TEMP\labtools-wrapper-audit-build"
git diff --check
git diff --stat
git status --short
git diff --cached --stat
```

Build may require available build dependencies. Do not change the lockfile to make an
unavailable check look passed. Review Markdown relative links locally as well; the
implementation environment checked file targets, not external URLs or heading anchors.

## Relevant commit message

After reviewing the docs and unrelated staged state, stage only this checkpoint:

```powershell
git add -- @changedPaths
git diff --cached --check
git diff --cached --stat
git diff --cached
git status --short
git commit `
  -m 'Audit device wrappers and define staged lifecycle repairs' `
  -m 'Document per-wrapper failure evidence, consumer inventory, rewrite decisions and fake/physical acceptance requirements.' `
  -m 'Prioritise fixture-backed IDQ parser hardening and bounded ITC transport lifecycle work without changing hardware commands.' `
  -m 'Refresh roadmap, handover and deployment caveats; keep acquisition changes blocked pending executed QtWidgets acceptance.'
```

git commit includes the whole index: inspect unrelated staged changes before running.
No commit or staging was performed by this audit or installer.

## Remaining acceptance and one next bounded task

Windows/QtWidgets acceptance is still open. Physical LabJack calibration/pins/gate,
IDQ firmware/socket behaviour, HORIBA SDK/shutter timing, SC10 state, ITC output policy,
camera partial-start teardown and Kinesis native-unit movement remain unvalidated.
The deployment guide is proposed manual guidance, not a deployed release/security system.

**Next fixture-independent implementation: W1 ITC transport lifecycle only.** Follow
the repair plan: startup handle cleanup, independent teardown, body/primary exception
retention and whole-wrapper fake-PyVISA tests. Do not add output-off/TEC-off commands or
combine with finite-limit policy, map allocation or another wrapper. If representative
IDQ histogram response fixtures become available, prioritize that isolated P0 parser
checkpoint instead; do not invent grammar or silently leave the finding untracked.

The separate acquisition lane remains: execute/fix Qt gate, then collision-safe map
allocation. Passing an ITC fake test does not satisfy that Qt gate.
