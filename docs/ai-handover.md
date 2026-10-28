# AI handover

Start here. This repository controls physical laboratory instruments. Reliability,
resource ownership and explicit failure/cleanup behavior outrank uniform wrappers.
Inspect actual code before editing; do not assume another inaccessible run exists.

## Repository/checkpoint identity

Input: labtools_source_20261027_175907.txt, 99 exported files, snapshot timestamp
2026-10-27T17:59:07.2679251+00:00. Reported branch feature/shared-instrument-session;
reported HEAD 385df0dbfbc58f61200030c6165238404d92bed2. The snapshot already contains
uncommitted changes to acquisition/intensity_map.py and runtime/session.py, plus
untracked shared-map-backend docs/service/provider/tests. Preserve that baseline.
apply_labtools_shared_backend.py appears in snapshot Git status but was not exported.
No original .git history, uv.lock or vendor directory was supplied. The reconstruction
used a synthetic Git baseline solely for diff review; its commit is NOT user history.
No user branch was switched, staged, committed, merged or pushed by this task.

## Authoritative sources, not competing plans

- [Architecture and decisions](architecture.md): current vs target, contracts,
  ownership, spectrum policy, simulation/configuration/safety and ADRs.
- [Development conventions](development-conventions.md): mandatory change rules.
- [Roadmap and wrapper matrix](refactor-roadmap.md): eight bounded phases,
  prerequisites, tests, acceptance, hardware gates, risks and checkpoints.
- [Development commands](development.md) and [commands](commands.md): existing tools.
- [Spectroscopy reference](hardware/spectroscopy.md): technical context, with known
  wrapper/API discrepancies explicitly registered in the roadmap.

Historical batch notes are retained for technical details, not current task order.
Report documentation/code conflicts. Do not redesign architecture during a bounded
phase; explain any necessary change and its evidence before broadening scope.

## This batch: implemented, not to be redone

- config/spectrum.py: immutable validated SpectrumSettings with explicit backend
  and maintainer configuration_id; conservative dark compatibility signature.
- acquisition/spectrum_service.py: RangeBackend contract, SpectrumService,
  immutable owned DarkRecord/SpectrumResult, canonical opt-in correction policy,
  pre-open validation and cooperative cancellation boundaries.
- runtime/spectrum_backend.py: explicit lazy real/synthetic factory; real context
  delegates existing range capture and guarantees a disconnect attempt even after
  connect/configure failure. It preserves a primary error if disconnect also raises.
- simulation/spectrum.py: deterministic toy range backend, no native imports.
- io/spectrum_records.py: strict schema-v1 NPZ dark load/save, result export,
  JSON metadata, no pickle, synthetic labels, exclusive-create and ordinary
  failed-write cleanup. Result loading and crash-atomic archives are not implemented.
- examples/experiments/simulate_spectrum_service.py: representative headless path.
- devices/labjack_u6.py: cleanup after returned-handle calibration failure,
  primary-error preservation and idempotent successful close; no output commands.
- tests/test_spectrum_service.py and test_labjack_lifecycle.py: 60 new cases.
- Four canonical architecture/conventions/roadmap/handover documents; index and
  historical-note cross-references. Existing session/shared-map code was preserved.

## Explicitly NOT completed

Legacy spectrum GUI still bypasses the new service and accepts unverified CSV
DarkSpectrum data. Its stale-dark/median/worker-lifecycle issues remain. The new
service does not fix a GUI that has not adopted it. No persistent HORIBA connection,
main GUI, production shared-window wiring, global IDQ coordination, shared map
simulation composition, generic profile framework or broad wrapper migration.

Alignment source is absent from the exported files despite the HEAD..main report.
Review actual main-branch files later; do not recreate their API from that report.
The requested 0.02 s floor conflicts with wrapper configure minima 0.065/0.100 s.
No minimum was lowered and no direct-setter bypass was introduced.

## Non-negotiable continuation constraints

Keep InstrumentSession as the synchronous process-local reservation owner. Use
narrow service protocols and injected factories, no singleton/universal ABC.
HORIBA connect/use/disconnect must stay on one asyncio loop. Do not cache it across
AsyncTaskRunner jobs. Persistent reuse requires Phase 4's dedicated worker.
Current spectrum service is per-operation, not a shared ownership manager: do not
run competing real service calls or standalone tools on the same device.
Do not fabricate calibration/temperature validity, raw data after nonlinear
fresh-dark reduction, or legacy CSV provenance. Preserve vendor commands/limits,
map schema 1/checkpoint signatures, QSettings keys and compatibility exports.
Do not claim software interlocks or simulation prove physical safety.

## Validation evidence for this batch

Environment: Linux, Python 3.12.15, NumPy 1.26.4, matplotlib 3.8.4, pytest 9.1.1,
setuptools 84.0.0. These NumPy/matplotlib versions are BELOW pyproject minimums.
No uv sync or locked dependency acceptance is claimed. No dependency constraints
were weakened to make tests pass. No physical device was connected.

Executed from reconstructed root:

```sh
PYTHONPATH=src MPLBACKEND=Agg PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
# 263 passed, 2 skipped, 172 third-party matplotlib/pyparsing warnings.
PYTHONPATH=src python -m compileall -q src tests examples
PYTHONPATH=src python -m labtools --help
PYTHONPATH=src python examples/experiments/simulate_spectrum_service.py
# SYNTHETIC DATA ONLY, 64 points; no files without --output.
PYTHONPATH=src python -c "from setuptools.build_meta import build_wheel; build_wheel('/tmp/labtools-wheel')"
# Wheel build passed using installed setuptools, without resolving dependencies.
git diff --check
```

Baseline before edits: 203 passed, 2 skipped, same 172 warnings. Hardware modules
are excluded before collection unless --run-hardware; they are not counted among
the two skips. Those skips are test_qt_controllers.py and test_gui_lifecycle.py,
both missing PyQt6. No Qt GUI acceptance claim. Ruff was unavailable; offline cache
lookup failed and registry access returned HTTP 403. Lint/format checks therefore
DID NOT RUN. No configured type checker exists. Package build does not establish
installation of the declared hardware dependencies or Windows DLL loading.

Run on the existing working laboratory environment, without changing its external
environment/copy-mode setup:

```powershell
uv run --no-sync python -m pytest -q
uv run --no-sync python -m pytest tests/test_spectrum_service.py tests/test_labjack_lifecycle.py -q
uv run --no-sync python -m pytest tests/test_qt_controllers.py tests/test_gui_lifecycle.py -q
uv run --no-sync ruff check src tests
uv run --no-sync ruff format --check src tests
uv run --no-sync python -m labtools --help
git diff --check
git status --short
```

Whole-tree lint/format may expose inherited debt; separate baseline findings from
new ones and do not mix an automatic whole-tree rewrite into this checkpoint.
For a clean environment use the actual repository's lockfile if present; the
snapshot did not include it. Never run --run-hardware or diagnostic scripts
without the operator's reviewed setup and explicit permission.


## Phase 1 spectrum GUI checkpoint, 28 October 2026
The ordinary spectrum GUI now uses the injected SpectrumService, SpectrumSettings, DarkRecord and SpectrumResult for connection tests, reusable dark capture and acquisition. It requires a maintainer-supplied configuration_id; the standalone launcher reads LABTOOLS_SPECTRUM_CONFIGURATION_ID and refuses to start without it. No persistent HORIBA connection or alignment feature was introduced.

Dark archives are provenance-bearing NPZ files. Legacy CSV is not converted into a DarkRecord and the GUI explains that recapture is required. Dark enablement is separate from the retained record, and relevant settings changes display valid/stale status. Median requires three frames. Result NPZ metadata and CSV/PNG derivatives are generated from the immutable SpectrumResult; collision-safe suffixes avoid overwriting prior outputs. No spectrum-specific QSettings keys existed in the supplied GUI, so none were invented; QSettings used by other tools were untouched.

AsyncTaskRunner now handles asyncio.CancelledError explicitly. The window retains its QThread/runner and busy state until QThread.finished, rejects close while cleanup is active, and permits restart only after release. New offscreen fake-service tests cover stale settings, disabled subtraction with retained data, NPZ load, legacy CSV messaging, immutable saved metadata, success/error/cancel/close/restart and minimum frame count. Existing service tests continue to cover NPZ roundtrip and native-import isolation for simulation.

Validation in the reconstruction environment: `PYTHONPATH=src MPLBACKEND=Agg PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` reported 263 passed, 3 skipped and 172 inherited matplotlib/pyparsing warnings. The skips are Qt modules because PyQt6/QtWidgets is unavailable here, including the new Phase 1 GUI suite. GUI acceptance is therefore NOT claimed. No hardware or diagnostic script was run. Run the Qt tests on the laboratory environment before committing or release.

## NEXT TASK: execute Phase 1 Qt acceptance, then review checkpoint
Run the new offscreen spectrum GUI tests plus the existing Qt controller/lifecycle tests in the laboratory environment. If they pass, inspect the diff/status and create the reviewed Phase 1 checkpoint only. Do not begin alignment or persistent connection work in the same commit.



Migrate the ordinary spectrum GUI to SpectrumService/DarkRecord, with fake/offscreen
Qt tests, before implementing alignment or persistent connection reuse. Full scope
and acceptance are in roadmap Phase 1. Hardware is not needed for fake tests;
physical and operator-workflow acceptance are required before release.

### Exact prompt for the next model

```text
Inspect the attached current labtools repository first. Read docs/ai-handover.md,
docs/architecture.md, docs/development-conventions.md and Phase 1 of
docs/refactor-roadmap.md. Treat actual code as authoritative; report conflicts.
Implement Phase 1 only: migrate the ordinary spectrum GUI to the existing
SpectrumService, SpectrumSettings, DarkRecord and SpectrumResult. Do not redesign
the architecture, rewrite wrappers, build alignment or introduce persistent
connections. Preserve layout, launch/import compatibility, QSettings, laser
controls, hardware commands and preset exposure minima.
Inject the service and a maintainer-supplied configuration_id. Snapshot settings
on the UI thread. Use provenance-bearing NPZ darks; do not assign current settings
to legacy CSV and call it validated. Explain required recapture and show validity
when settings change. Keep subtraction enablement separate from stored dark data.
Fix median minimum to three. Preserve raw/corrected identity and export metadata
from the immutable result. Retain existing CSV/PNG exports as derivatives.
Handle asyncio.CancelledError explicitly, retain worker ownership/busy state until
QThread.finished, and test cancel/error/close/restart with fake devices offscreen.
Tests must cover stale dark settings, disabled subtraction, NPZ roundtrip, legacy
CSV messaging, saved metadata and no native imports in synthetic mode. Run the
full offline suite and available lint/format/build checks; report skips and gaps.
If Qt cannot run, do not claim GUI acceptance or replace tests with a narrative.
Update handover/roadmap to match actual code, inspect Git diff/status, and stop at
one reviewed checkpoint. Do not commit, merge or run hardware automatically.
Return changed files, validation results, remaining risks and a commit message.
```

### Reusable later-phase prompt template

```text
Inspect the current repository and Git status. Read docs/ai-handover.md,
docs/architecture.md, docs/development-conventions.md and roadmap Phase <N>.
Implement only <bounded objective/subtask>. Prerequisites: <verified prerequisites>.
Use the existing extension points: <modules/contracts>. Preserve <listed APIs,
commands, units, limits, output/checkpoint formats and cleanup order>.
Do not reopen architectural decisions, migrate unrelated wrappers or claim planned
features exist. Report code/documentation conflicts and justified scope changes.
Add <specific fake/synthetic/Qt/contract tests> and verify <acceptance criteria>.
Hardware requirement: <none for software tests / explicit reviewed validation>.
Do not run hardware automatically. Run configured available checks and report
failures, skips, dependency differences and unavailable tools honestly.
Update the canonical roadmap/handover with exact status and the next bounded task.
Inspect diff/status and stop at <checkpoint>. Do not commit or merge automatically.
Deliver actual changes, tests, validation evidence, risks and a commit message.
```

## Git/apply workflow

Close GUIs and inspect current status. Commit/back up existing tested work before
applying another batch where practical. The delivered guarded installer checks
all affected baselines, refuses main/master/detached HEAD, backs up exact original
bytes outside the repository, and never stages/commits/changes branches. It permits
unrelated dirty files because the supplied baseline itself is dirty. Review its
printed paths. Apply once; do not also apply the review patch. Run the laboratory
checks above, review diff/status, then choose the checkpoint commit yourself.
Suggested message: Add spectrum service foundations and authoritative refactor handover.

## Unresolved and hardware gates

See roadmap's final register for full ownership. Highest priority: legacy GUI dark
migration; missing alignment source and exposure-floor evidence; HORIBA partial
startup/disconnect suppressions; SC10/ITC output-state cleanup policy; IDQ socket/
DLT ownership and histogram parser; shared manual/map wiring and profile approval.
Software tests do not validate real shutter/TTL timing, optical darkness, physical
safe states, calibration, Windows drivers or native abort feasibility. Changed
LabJack startup/close behavior and the real spectrum adapter require hardware
acceptance before merging for laboratory use. External script consumers are OPEN.


## Phase 2 checkpoint, 28 October 2026
Implemented the bounded shared manual-mirror/map composition using the existing InstrumentSession and LabJackService path. Added detached status snapshots, a narrow ManualMirrorService, one SharedMirrorMapApplication composition root, injected map acquisition, and shared-mode laser-control disabling. Standalone launch paths and defaults are unchanged. No IDQ session ownership, HORIBA worker, alignment, complete launcher or broad wrapper cleanup was added.

Offline validation in the reconstruction environment: focused Phase 2/session/shared-map tests and the full suite passed after one test-expectation correction; final exact results are recorded in the delivery report. Qt modules may skip where PyQt6/QtWidgets is unavailable. No hardware or diagnostic scripts were run. Physical LabJack connection reuse, mirror voltage behaviour, DIO gate polarity/timing and cleanup ordering still require reviewed laboratory acceptance.

Next bounded task: Phase 3 shared simulation state as a separate checkpoint before IDQ count-service ownership, preserving map model/version and checkpoint signatures.
