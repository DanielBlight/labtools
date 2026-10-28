# Development handover: comparative audit checkpoint

## Starting identity and evidence

Current snapshot: `labtools_source_20261028_150404.txt`, created
2026-10-28T15:04:04.4560095Z, branch `feature/shared-instrument-session`, HEAD
`3e5a0c9f41edbbf692faabd9ef5cd6e9b2bc8aab`, clean index/worktree and upstream +0/-0.
Baseline snapshot: `labtools_source_20261027_175907.txt`, created
2026-10-27T17:59:07.2679251+00:00, HEAD
`385df0dbfbc58f61200030c6165238404d92bed2`, with recorded uncommitted shared-backend work.
These are snapshot identities, not a claim about the user's live checkout. Inspect
actual Git status before any edit. No Git mutation or hardware operation was performed.

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

## Validation in this audit environment

Python 3.12.15, installed scientific packages rather than a reproduced uv.lock environment.
Baseline: 203 passed, 2 skipped, 172 warnings.
Current before fixes: 292 passed, 4 skipped, 172 warnings.
Corrected: 303 passed, 4 skipped, 172 warnings.
New audit regressions: 11 passed. Earlier focused affected selection: 62 passed.
Four Qt-dependent modules skipped because PyQt6 is unavailable. Ruff unavailable;
no Ruff-clean claim. Matplotlib/pyparsing deprecation warnings remain.
Compilation, CLI help, local Markdown links, TOML parsing, native-free smoke and wheel
build are recorded in the audit report. Lockfile/pyproject were inspected and unchanged;
the exact Windows locked environment still requires local validation.

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = "offscreen"
$env:MPLBACKEND = "Agg"
uv run --no-sync python -m pytest -q
uv run --no-sync python -m compileall -q src tests examples
uv run --no-sync python -m labtools --help
git diff --check
git status --short
```

Run Ruff on the installer's changed Python list, then the intended repository policy.
Do not use unsafe fixes or mix a whole-tree formatting sweep into this checkpoint.
Remove QT_QPA_PLATFORM=offscreen before interactive GUI testing.

## Physical validation still required

LabJack wiring/voltage calibration and gate timing; IDQ firmware/channel/timeout/socket
lifecycle; HORIBA preset discovery, shutter/dark correctness, exposure timing and SDK
loop teardown. Existing SC10/ITC/camera/stage and hazardous anneal/hyperspectral paths
are not certified by these tests. No physical endpoint was contacted.

## Next bounded task

Finish Windows/Qt acceptance and alignment lifecycle hardening before a shared launcher:
run the skipped modules, test busy/fault/deferred close with blocked fake operations,
and verify repeated start/stop/private-versus-injected ownership. Address any failures
in one checkpoint. Do not combine this with persistent HORIBA connections, new launcher
UI, IDQ streaming, profile generalization or broad wrapper rewrites.

Known follow-ups: same-second map output-directory collision; fixed shared IDQ IPv4
policy and explicit counter-provider compatibility; native wrapper disconnect-error
visibility; tracked migration/data artifacts. No deletion of those artifacts was made.

## Git workflow

Installer targets the exact current snapshot, including any future intended dirty
state only if its affected bytes match. It does not stage/commit/merge/push/reset.
Review changed files and preserve unrelated changes. Keep backups outside the repo.
Do not merge until local Ruff/Qt acceptance and required physical review are recorded.
