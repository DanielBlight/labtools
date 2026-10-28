# Development handover: deployment guidance and open Qt gate

## Starting identity and evidence

Current input: `labtools_source_20261028_170656.txt`, created
2026-10-28T17:06:56.8575069Z, branch `feature/shared-instrument-session`, HEAD
`a439207b4b6d6aec2fbf3575d2fa155893d318a3`, upstream +2/-0.
Recorded dirty state: untracked `apply_labtools_alignment_lifecycle.py` and
`apply_labtools_comparative_audit.py`; tracked worktree/index otherwise clean.
No local Windows test output was attached. A commit containing test source is not
proof that the QtWidgets acceptance cases ran. Actual live Git status is authoritative.

This checkpoint adds deployment documentation only. No production/test Python, lockfile,
profile, driver, account, ACL, installed lab-PC environment or hardware was changed.
The collision-safe map allocation task remains blocked by the explicit Qt gate.

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

## Next bounded task

First run the supplied QtWidgets acceptance cases on the Windows checkout and fix only
failures from that gate. If they all execute and pass, the next implementation task is
collision-safe intensity-map output-directory allocation: two new runs in the same
second must not fail or overwrite data. Preserve the legacy first directory name,
metadata, checkpoint/resume schema and deterministic output. Add concurrent-allocation
and immediate-retry tests. Keep this separate from launcher Phase 7, persistent HORIBA
connections, IDQ streaming and broad wrapper rewrites.

Remaining reviews: shared IDQ explicit counter-provider compatibility and IPv4 policy;
native disconnect-error visibility; tracked artifacts; physical acceptance. No unrelated
artifact was deleted. The comparative audit is a historical record, not current counts.

## Git workflow

Installer targets the exact current snapshot, including any future intended dirty
state only if its affected bytes match. It does not stage/commit/merge/push/reset.
Review changed files and preserve unrelated changes. Keep backups outside the repo.
Do not merge until local Ruff/Qt acceptance and required physical review are recorded.

## Deployment-documentation checkpoint and gate rerun

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
