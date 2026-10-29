# Development handover: device-wrapper audit and open Qt gate

## Starting identity and evidence

Current input: `labtools_source_20261028_215033.txt`, created
2026-10-28T21:50:33.8045255Z, branch `feature/shared-instrument-session`, HEAD
`ceaabec9ea4882c1882f71facf604a04099a5992`, upstream +0/-0.
Tracked worktree/index are recorded clean. Three installers are untracked:
`apply_labtools_alignment_lifecycle.py`, `apply_labtools_comparative_audit.py`,
`apply_labtools_deployment_docs.py`. Preserve these and any live unrelated changes.
No separate local Qt acceptance pass output is embedded. Actual live status is authoritative.

This checkpoint is documentation-only: an independent device-wrapper audit and bounded
repair plan. No production/test Python, dependency, profile, driver, account, ACL,
lab-PC environment, Git history/index or hardware was changed. The QtWidgets gate
remains open, so collision-safe map allocation has not advanced.

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

Read [wrapper audit](device-wrapper-audit.md), [repair plan](device-wrapper-repair-plan.md)
and [checkpoint](wrapper-audit-checkpoint.md).

Acquisition lane: first execute/fix the QtWidgets gate with complete local output.
Only after it passes, implement collision-safe map output directories as already planned.
Do not treat committed test source, bytecode or a zero exit code with skips as a pass.

Independent wrapper lane (per the user's added request): next fixture-independent
implementation is W1 ITC transport startup/teardown only. Preserve public API and all
output/TEC/current commands; add whole-wrapper fake-PyVISA failure tests. Do not combine
with finite-limit policy, HORIBA, IDQ streaming, map allocation or launcher changes.
IDQ histogram eval is a P0 parser finding: prioritize an isolated parser fix when
representative accepted-response fixtures are available; do not invent firmware grammar.

The audit recommends targeted repairs, not a blanket rewrite. DLT/IDQ internal ownership
needs staged decomposition behind the existing facade. Existing style passes do not
establish lifecycle correctness. Keep the physical acceptance and deployment gates.

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

## Current wrapper-audit validation

Qt gate rerun: 15 passed / 4 skipped. Full offline suite: 318 passed / 4 skipped,
172 inherited warnings. All four QtWidgets modules still skip (libGL.so.1 missing).
Eight extracted-method fake-handle probes confirm specific ITC/HORIBA/DAC/UC480 defects;
these are not whole-module or hardware tests. Device Ruff check passes and all 12 device
Python files are formatted. See the checkpoint for compile/build/import/link evidence.
No wrapper rewrite or collision fix is implemented by this documentation checkpoint.
Earlier counts and deployment statements above remain historical evidence where labelled.
