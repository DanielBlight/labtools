# Comparative labtools audit and correction checkpoint

## 1. Executive assessment

The recent work establishes useful service/ownership seams and substantially improves
headless regression coverage. It is not a completed unified instrument application.
The green suite concealed startup/cleanup and backend-isolation gaps; this audit makes
bounded corrections rather than adding another feature phase. Recommendation: do not
merge yet. Complete local Ruff and Windows/Qt lifecycle acceptance, then record the
required physical validation before production deployment.

This is a source-snapshot audit, not an inspection of the user's live Git repository.
No hardware, diagnostics, network endpoints or Git mutation were used. The audit is
not exhaustive formal verification of every device wrapper or vendor example.

## 2. Exact snapshot identities

- Baseline: labtools_source_20261027_175907.txt, created
  2026-10-27T17:59:07.2679251+00:00, branch feature/shared-instrument-session,
  HEAD 385df0dbfbc58f61200030c6165238404d92bed2.
- Current: labtools_source_20261028_150404.txt, created
  2026-10-28T15:04:04.4560095Z, same branch,
  HEAD 3e5a0c9f41edbbf692faabd9ef5cd6e9b2bc8aab, upstream +0/-0,
  clean recorded index/worktree.

Baseline recorded status (not a clean committed baseline):

```text
 M src/labtools/acquisition/intensity_map.py
 M src/labtools/runtime/session.py
?? apply_labtools_shared_backend.py
?? docs/shared-map-backend.md
?? src/labtools/runtime/labjack_service.py
?? src/labtools/runtime/shared_map.py
?? tests/test_session_cleanup.py
?? tests/test_shared_map_backend.py
```

The comparison is against those actual baseline file contents, including uncommitted
work, not simply against commit 385df0d. Baseline contains 99 embedded files; current
contains 183. Their union has 184 paths: 85 current-only, one baseline-only, 41 modified,
24 Python AST-equivalent formatting/comment changes, and 33 identical reconstructed
files. These are snapshot coverage counts, not Git add/delete counts. In particular,
uv.lock/vendor/data/migration coverage differs, and absence of .python-version in the
current export does not alone prove a repository deletion.

## 3. Conflicts found before correction

- Handover still identified 5225d07 and 267 tests; architecture mixed 385df0d with
  later implementation. Those are historical, not the current source identity.
- Worker/alignment appeared both implemented and planned in different documents.
- Handover proposed a Phase 5a launcher while the roadmap's Phase 5 was wrapper
  reliability and Phase 7 was the shared launcher.
- 'Persistent HORIBA' meant a persistent loop, not a persistent physical connection.
- Shared IDQ composition exposes one fixed IPv4 address, not general alias resolution
  or dynamic multiple-controller registration. Existing socket code does not prove
  that hostnames are universally unsupported; the shared IPv4 policy is a restriction.
- Alignment's GUI-only exposure validation was stronger than direct service validation.
- Simulation alignment's default options provider imported the native wrapper.
- Alignment uses a separate immutable AlignmentResult, not the range SpectrumResult.
  This is documented rather than misrepresented as identical contracts.
- Qt test source existed but was not executed in this environment. Earlier completion
  claims did not establish Qt/physical acceptance.

## 4. Change inventory by subsystem

### Structure, commands, packaging and artifacts

The src layout, CLI, workspace and compatibility shims already existed in the baseline.
Recent work adds spectrum config/service/persistence/simulation and shared application
modules, handover/conventions/roadmap, worker and alignment. Console names remain
standalone; alignment has a module entry point, not a registered gui alignment command.
Source imports can use PYTHONPATH when an existing environment lacks installed scripts.
pyproject adds vendor Ruff exclusion; dependency metadata is retained. uv.lock is
current-only in export coverage, so its historical dependency delta cannot be proven.
Tracked migration originals, metadata under data/, snapshot helper and project_upload
are visible. They were not deleted: source snapshots cannot establish whether every
artifact is intentional or supply omitted binary data. Review artifact policy separately.

### Session, LabJack, manual/map and simulation

Baseline already includes the session and uncommitted shared-map provider. Current adds
detached status, application/manual service injection and shared simulation composition.
Mirror/gate alias the LabJack physical resource. The session checks queued calls and
retains in-flight counts on the worker, so caller interruption cannot release a running
command. Reviewed cleanup remains possible after faults. Map cleanup stays checkpoint,
home, gate-close; zero volts is not a safe-state certification. Shared simulation uses
one mirror/gate state, per-map deterministic counter and unchanged model/signatures.
Audit resets failure-injection measurement count per map rather than app lifetime.

### IDQ

Shared real maps add a narrow count service and lease proxy; construct/connect/use/
close run on the session worker. LabJack and IDQ are reserved atomically. Standalone
real_counter still opens per map on its acquisition thread. Direct IDQ smoke tests,
histogram/timestamp tests and vendor examples remain separate. DLT, histogram and
coincidence ownership are not migrated. Partial connect cleanup is corrected here.
The real wrapper still suppresses some disconnect failures internally; the adapter
cannot promise error visibility that the wrapper does not provide.

### Spectrum and persistence

Current adds immutable settings/results/darks, service orchestration, NPZ persistence,
explicit simulation and ordinary GUI migration. Legacy processing/dark APIs remain.
NPZ archives are pickle-free; CSV cannot be promoted to provenance-bearing dark data.
Fresh-dark range raw data may be unavailable by design. Median/sigma-clip minimum is
three. Ordinary GUI retains its own operation-scoped runner and standalone lifecycle.
Keep io/; defer map persistence extraction to a separately tested schema-compatible task.

### Worker and alignment

Current adds one lazy loop/thread executor with reject-not-queue policy and immutable
status. Alignment submits sequential complete jobs with stable owner label, settings
snapshots and job polling. Injected workers survive window close; private workers close
after active cleanup. Each frame still reconnects/configures/moves/acquires/disconnects.
This is not a high-rate persistent connection implementation. Separate worker instances
are not coordinated. Native SDK calls cannot be forcibly cancelled by this design.

### Formatting versus behaviour

24 common Python files have identical parsed ASTs after formatting/comment changes.
Other modified files include annotations/import changes, timezone-aware legacy runner
metadata, GUI/service migration and session status/reservation changes. AST equality
is useful evidence against accidental algorithm changes, not a proof of runtime
identity for comments/tooling, imports or vendor environment behaviour.

## 5. Ranked findings and disposition

Critical: no new critical issue was demonstrated offline. This is not a safety approval.

High, corrected:
1. IDQ connect failure could leave a partially created controller uncleaned. Attempt
   disconnect, preserve original failure and attach cleanup failure notes.
2. Worker close during loop startup could miss the loop and join a thread that later
   ran forever. Serialize close, wait for startup publication, then stop/join.
3. Loop startup failure could strand callers waiting for readiness. Publish the error.
4. Alignment adapters lacked explicit opposite-backend rejection. Reject before factory.
5. Exposure floors could be bypassed through direct alignment service requests.
   Enforce 0.065/0.1 s in native-free settings validation as well as GUI/wrapper.
6. Cancelled real jobs with failed disconnect could advertise available. Preserve the
   cancellation but fault the worker when backend cleanup records failure.

Medium, corrected:
7. Simulated alignment loaded the real wrapper to obtain option tokens. Extract only
   literal option data into native-free config, consumed by wrapper and alignment.
   Hardware discovery, ROI, grating and mirror commands remain in the wrapper.
8. Worker accepted mismatched settings/backend and could falsely classify failures.
   Reject before starting its thread; GUI also checks injected worker backend.
9. Shared simulation failure injection counted app-lifetime points. Reset per map.
10. Worker self-join/concurrent close and stale active-future assignment were fragile.
    Guard self-close, serialize close and publish active future under the lock.
11. Alignment submission errors and fault presentation could leave misleading UI state.
    Restore controls and explicitly report application teardown; avoid a new modal
    error dialog after deferred close has already been requested.

Medium, deferred:
- Same-second map directory creation can collide on immediate retry. No naming/schema
  change is bundled here; add collision-safe allocation in a bounded follow-up.
- A real SharedMirrorMapApplication explicit counter_provider conflicts with its
  registered counter_resource. Clarify/deprecate that injection API with compatibility
  tests rather than silently bypassing physical ownership.
- IPv4-only fixed-controller policy and swallowed native disconnect errors need
  deliberate compatibility/failure-policy review.
- Missing Windows/Qt execution and incomplete blocked-job GUI coverage remain merge gates.
- Real HORIBA reconnect-per-frame performance and SDK shutdown behaviour remain unverified.

Low/documentation, corrected:
- Stale identities/test results, conflicting phase order and misleading persistence
  terminology. Reconcile current docs; label historical batch records.

Low, deferred:
- Artifact tracking/cleanup, compatibility retirement and map persistence extraction.

## 6. Retained unchanged and why

InstrumentSession execution/cleanup mechanism, map checkpoint/output schemas and
signatures, deterministic scene math, range processing, NPZ persistence and ordinary
spectrum GUI were retained. Existing tests exercise these contracts and this audit
found no evidence justifying broad rewrites. Vendor files and hardware command logic
were not modified. Standalone commands, QSettings, pins and physical limits stay.

## 7. Modified/replaced work and why

The installer changes narrow lifecycle/validation boundaries and documentation only.
The wrapper's option literals move to shared native-free configuration; its hardware
preset fields and command sequences do not change. No universal device framework,
new registry, shared launcher or persistent connection cache is introduced.

## 8. Final ownership model

InstrumentSession owns registered synchronous physical services. Shared maps hold
LabJack+IDQ reservations through cleanup. SpectrumWorker is a loop-affine complete-job
executor; only clients injected with the same instance serialize. Each backend context
owns its operation-scoped connection. Tool close releases client work; application
shutdown owns shared service teardown. Native blocking calls have no new deadline.

## 9-11. Files changed by this audit

The exact list is appended below and available from the installer --list/--list-python.
Production changes are under src/, tests under tests/, and current/historical guidance
under docs/. No pyproject/uv.lock/vendor/data changes are made by the installer.

## 12-16. Validation evidence

- Baseline reconstructed suite: 203 passed, 2 skipped, 172 warnings.
- Current reconstructed suite before fixes: 292 passed, 4 skipped, 172 warnings.
- Corrected complete suite: 303 passed, 4 skipped, 172 warnings.
- New audit regressions: 11 passed.
- Earlier affected alignment/worker/processing/shared-simulation selection: 62 passed.
- Compileall src/tests/examples: passed.
- CLI help: passed.
- Native-free simulation smoke with driver imports blocked: passed, 64 samples.
- pyproject.toml and uv.lock parsing: passed; unchanged by audit.
- Wheel via installed setuptools backend: lab_tools-0.1.0-py3-none-any.whl built.
- Local relative Markdown link targets: 76 checked, zero missing. Heading anchors
  and external URLs are not validated.
- Installer: check/apply/exact-byte CRLF rollback, injected partial-write restoration
  and main-branch refusal passed in a temporary copy with read-only Git responses mocked.
- git diff --no-index --check against reconstructed current input: checked, not live Git.
- Ruff format/check: unavailable, NOT passed or claimed clean. Run locally.

Environment: Python 3.12.15 with preinstalled packages, not the exact locked Windows
Python 3.12.6 environment recorded in the snapshot. Lockfile was inspected, not synced.
PyQt6 is absent. Skipped modules: test_alignment_gui, test_spectrum_gui_phase1,
test_gui_lifecycle and test_qt_controllers. New GUI tests are supplied but not executed.
Hardware modules are excluded by the existing pre-import opt-in guard. No hardware
fixture or diagnostic was invoked. Warnings are Matplotlib/pyparsing deprecations.
Wheel build warns that installed packaging is old for license-expression validation.
No dependency installation or lock update was attempted.

## 17. Compatibility and regression risks

No map schema/signature, deterministic model, output array, detector token, physical
command, unit, pin, QSettings or launch path is intentionally changed. Intentional
failure-path changes: stricter early alignment validation, cleanup on partial IDQ
connect, faulting cancellation after failed disconnect, and worker startup/close guards.
Synthetic measurement diagnostics now describe the current map, not lifetime totals.
Shared preset data extraction needs real-wrapper import/Qt acceptance on Windows.
The cancellation-cleanup marker is internal and tested, not a public exception API.
Native wrapper swallowing of errors remains outside the guarantee.

## 18. Physical validation required

- LabJack/mirror/gate: wiring, DAC calibration, limits, polarity, gate timing, home
  meaning and failure cleanup. Zero volts is not inherently safe.
- IDQ: address/firmware, channel tokens, thresholds, integration/count order, timeout,
  socket lifetime/reuse and close after network loss. No endpoint was contacted.
- HORIBA: detector discovery, gain/speed tokens, preset exposure support, shutter dark
  correctness, wavelength readback, loop affinity and disconnect after failure.
- ITC/SC10/camera/stage/anneal/hyperspectral: existing hazardous workflows remain
  outside this audit's physical validation; no new certification is implied.

## 19. Git status and installer behaviour

Current supplied status is clean, branch feature/shared-instrument-session, upstream
+0/-0, HEAD 3e5a0c9f41edbbf692faabd9ef5cd6e9b2bc8aab. No staged changes are recorded.
Earlier deleted installer files are no longer dirty in this snapshot; do not restore
historical deletions. The live checkout cannot be inspected here. Expected installer
changes are exactly the list below, unstaged; existing unrelated index/worktree changes
remain untouched. Snapshot exports do not contain a .git directory.

## 20-22. Merge recommendation and next task

Not ready to merge solely on this audit. Local Ruff and skipped Qt lifecycle tests
must pass, and physical acceptance/release decisions must be recorded by the maintainer.
Next bounded task: Windows/Qt alignment lifecycle acceptance and blocked-job regression
coverage, before launcher development. Add collision-safe map directory allocation as
its own small reliability checkpoint. Keep launcher Phase 7, wrapper reviews Phase 5.
Defer persistent physical HORIBA connections, IDQ streaming/DLT/histograms, new devices,
operator-profile expansion, broad formatting, artifact deletion and io extraction.

## 23. Recommended commit

Subject: Harden shared instrument lifecycle and reconcile refactor status

Body:
- guard spectrum startup/shutdown, backend selection and cancelled cleanup faults
- clean up partial IDQ connection failures without replacing primary errors
- centralise native-free detector controls and enforce established exposure minima
- preserve map schemas, deterministic models and standalone device semantics
- add targeted offline regressions and reconcile architecture/roadmap/handover
- retain explicit Windows/Qt and physical acceptance gates

## 24-25. Installation, checking and rollback

Use the supplied apply_labtools_comparative_audit.py against the CURRENT snapshot.
The installer supports --check, --apply, --rollback, --list and --list-python.
It checks affected contents, refuses main/master/detached HEAD and new-file collisions,
backs up exact original bytes outside the repo and performs per-file atomic replacement
with restoration on an ordinary partial failure. Multi-file power-loss atomicity is not
claimed. Baseline matching tolerates BOM/line endings/trailing-newline export variance;
backups and rollback use exact bytes. Rollback refuses post-install edits, including
Ruff formatting changes. Keep the installer and backup until acceptance is complete.

Run from repository root, with GUIs closed:

```powershell
python .\apply_labtools_comparative_audit.py --check
python .\apply_labtools_comparative_audit.py --apply
$changedPython = @(python .\apply_labtools_comparative_audit.py --list-python)
$changedPaths = @(python .\apply_labtools_comparative_audit.py --list)
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = "offscreen"
$env:MPLBACKEND = "Agg"
uv run --no-sync ruff format @changedPython
uv run --no-sync ruff check @changedPython
uv run --no-sync python -m pytest tests/test_comparative_audit.py tests/test_alignment_spectrum.py tests/test_alignment_gui.py tests/test_spectrum_worker_phase4a.py tests/test_spectrum_service.py tests/test_shared_idq_phase3b.py tests/test_shared_simulation_phase3a.py -q
uv run --no-sync python -m pytest -q
uv run --no-sync python -m compileall -q src tests examples
uv run --no-sync python -m labtools --help
uv build --wheel --out-dir "$env:TEMP\labtools-audit-build"
git diff --check
git diff --stat
git status --short
git diff --cached --stat
```

Run each validation command and stop if it fails. Do not treat the command list as an
automated gate. uv build can require locally available build dependencies; report an
unavailable build rather than changing the lockfile. The provided snapshot has no
permanent shared launcher; do not invent its command.

Rollback before subsequent edits, using the actual printed backup path:

```powershell
python .\apply_labtools_comparative_audit.py --rollback "ACTUAL_BACKUP_DIRECTORY"
```

After checks and review, stage only this checkpoint. Existing staged unrelated files
must be reviewed before git commit, which commits the whole index:

```powershell
git add -- @changedPaths
git diff --cached --check
git diff --cached --stat
git diff --cached
git status --short
git commit -m "Harden shared instrument lifecycle and reconcile refactor status" -m "Guard worker startup, backend isolation, partial IDQ cleanup and established exposure minima; add offline regressions and reconcile current development guidance."
```

No staging or commit was performed by the audit or installer. Retain backup and
installer outside the staged set; remove temporary files only after acceptance.

## Complete baseline/current embedded-file inventory

Statuses describe export contents, not a claim about missing binary or tracked files.

- `unchanged`: `.gitignore`
- `added`: `.labtools-migrations/intensity-map-simulation-v1/manifest.json`
- `added`: `.labtools-migrations/operator-workspace-v1/manifest.json`
- `added`: `.labtools-migrations/operator-workspace-v1/original/pyproject.toml`
- `added`: `.labtools-migrations/operator-workspace-v1/original/src/labtools/acquisition/laser_anneal.py`
- `added`: `.labtools-migrations/operator-workspace-v1/original/src/labtools/gui/laser_anneal_gui.py`
- `added`: `.labtools-migrations/reliability-v3/manifest.json`
- `absent-current`: `.python-version`
- `unchanged`: `CONTRIBUTING.md`
- `modified`: `README.md`
- `added`: `data/intensity_maps/2026-09-11_13-58-46/metadata.json`
- `modified`: `docs/README.md`
- `added`: `docs/ai-handover.md`
- `modified`: `docs/architecture.md`
- `unchanged`: `docs/commands.md`
- `added`: `docs/development-conventions.md`
- `modified`: `docs/development.md`
- `modified`: `docs/future-refactoring.md`
- `unchanged`: `docs/hardware/spectroscopy.md`
- `added`: `docs/horiba-alignment.md`
- `unchanged`: `docs/intensity-map-simulation.md`
- `modified`: `docs/next-recommendations.md`
- `unchanged`: `docs/operator-workspace.md`
- `modified`: `docs/refactor-notes.md`
- `added`: `docs/refactor-roadmap.md`
- `modified`: `docs/session-foundation.md`
- `modified`: `docs/shared-map-backend.md`
- `modified`: `docs/spectrum-refactor.md`
- `unchanged`: `examples/experiments/run_anneal_recipe.py`
- `added`: `examples/experiments/simulate_spectrum_service.py`
- `unchanged`: `examples/profiles/instrument.example.json`
- `unchanged`: `main.py`
- `added`: `new_labtools_snapshot.ps1`
- `added`: `project_upload.txt`
- `modified`: `pyproject.toml`
- `unchanged`: `scripts/camera/check_uc480_camera.py`
- `unchanged`: `scripts/horiba/check_horiba_configuration.py`
- `unchanged`: `scripts/horiba/check_horiba_shutter.py`
- `modified`: `scripts/horiba/check_horiba_slit_width.py`
- `unchanged`: `scripts/horiba/set_horiba_configuration.py`
- `unchanged`: `src/labtools/__init__.py`
- `format/comments-only`: `src/labtools/__main__.py`
- `unchanged`: `src/labtools/acquisition/__init__.py`
- `added`: `src/labtools/acquisition/alignment_spectrum.py`
- `modified`: `src/labtools/acquisition/intensity_map.py`
- `modified`: `src/labtools/acquisition/laser_anneal.py`
- `modified`: `src/labtools/acquisition/range_spectrum.py`
- `modified`: `src/labtools/acquisition/run_hyperspectral_scan.py`
- `added`: `src/labtools/acquisition/spectrum_service.py`
- `modified`: `src/labtools/cli.py`
- `unchanged`: `src/labtools/config/__init__.py`
- `format/comments-only`: `src/labtools/config/anneal_workspace.py`
- `format/comments-only`: `src/labtools/config/intensity_map.py`
- `format/comments-only`: `src/labtools/config/recipe_ui.py`
- `added`: `src/labtools/config/spectrum.py`
- `unchanged`: `src/labtools/devices/__init__.py`
- `format/comments-only`: `src/labtools/devices/horiba_spectrometer.py`
- `unchanged`: `src/labtools/devices/idq_time_controller/__init__.py`
- `unchanged`: `src/labtools/devices/idq_time_controller/controller.py`
- `modified`: `src/labtools/devices/idq_time_controller/dlt.py`
- `modified`: `src/labtools/devices/itc4000.py`
- `unchanged`: `src/labtools/devices/kinesis_rotation_stage.py`
- `modified`: `src/labtools/devices/labjack_u6.py`
- `unchanged`: `src/labtools/devices/sc10.py`
- `format/comments-only`: `src/labtools/devices/scanning_mirror.py`
- `unchanged`: `src/labtools/devices/spad_gate.py`
- `unchanged`: `src/labtools/devices/uc480_camera.py`
- `unchanged`: `src/labtools/gui/__init__.py`
- `added`: `src/labtools/gui/alignment_gui_horiba.py`
- `modified`: `src/labtools/gui/async_runner.py`
- `format/comments-only`: `src/labtools/gui/background.py`
- `modified`: `src/labtools/gui/intensity_map_gui.py`
- `modified`: `src/labtools/gui/laser_anneal_gui.py`
- `modified`: `src/labtools/gui/map_controller.py`
- `modified`: `src/labtools/gui/mirror_controller.py`
- `modified`: `src/labtools/gui/mirror_voltage_gui.py`
- `format/comments-only`: `src/labtools/gui/recipe_controls.py`
- `modified`: `src/labtools/gui/spectrum_gui_horiba.py`
- `unchanged`: `src/labtools/io/__init__.py`
- `added`: `src/labtools/io/spectrum_records.py`
- `format/comments-only`: `src/labtools/launchers.py`
- `modified`: `src/labtools/operator_cli.py`
- `unchanged`: `src/labtools/processing/__init__.py`
- `format/comments-only`: `src/labtools/processing/background.py`
- `format/comments-only`: `src/labtools/processing/dark_spectrum.py`
- `format/comments-only`: `src/labtools/processing/spectrum.py`
- `unchanged`: `src/labtools/runtime/__init__.py`
- `format/comments-only`: `src/labtools/runtime/cleanup.py`
- `format/comments-only`: `src/labtools/runtime/contracts.py`
- `added`: `src/labtools/runtime/idq_count_service.py`
- `modified`: `src/labtools/runtime/labjack_service.py`
- `format/comments-only`: `src/labtools/runtime/lazy_devices.py`
- `modified`: `src/labtools/runtime/map_devices.py`
- `format/comments-only`: `src/labtools/runtime/mirror_backend.py`
- `modified`: `src/labtools/runtime/session.py`
- `added`: `src/labtools/runtime/shared_application.py`
- `modified`: `src/labtools/runtime/shared_map.py`
- `added`: `src/labtools/runtime/spectrum_backend.py`
- `added`: `src/labtools/runtime/spectrum_worker.py`
- `unchanged`: `src/labtools/simulation/__init__.py`
- `modified`: `src/labtools/simulation/intensity_map.py`
- `format/comments-only`: `src/labtools/simulation/map_backend.py`
- `format/comments-only`: `src/labtools/simulation/map_devices.py`
- `added`: `src/labtools/simulation/shared_map.py`
- `added`: `src/labtools/simulation/spectrum.py`
- `unchanged`: `src/labtools/visualisation/__init__.py`
- `unchanged`: `src/labtools/visualisation/intensity_map.py`
- `format/comments-only`: `tests/conftest.py`
- `format/comments-only`: `tests/scan_pyvisa_idn.py`
- `added`: `tests/test_alignment_gui.py`
- `added`: `tests/test_alignment_spectrum.py`
- `format/comments-only`: `tests/test_anneal_workspace.py`
- `modified`: `tests/test_cleanup_failures.py`
- `modified`: `tests/test_gui_lifecycle.py`
- `unchanged`: `tests/test_idq_acquisition.py`
- `format/comments-only`: `tests/test_intensity_map_simulation.py`
- `unchanged`: `tests/test_intensity_map_visualisation.py`
- `added`: `tests/test_labjack_lifecycle.py`
- `modified`: `tests/test_project_structure.py`
- `format/comments-only`: `tests/test_qt_controllers.py`
- `format/comments-only`: `tests/test_reliability_regressions.py`
- `unchanged`: `tests/test_sc10_modes.py`
- `modified`: `tests/test_session_cleanup.py`
- `modified`: `tests/test_session_core.py`
- `added`: `tests/test_shared_application_phase2.py`
- `added`: `tests/test_shared_idq_phase3b.py`
- `modified`: `tests/test_shared_map_backend.py`
- `added`: `tests/test_shared_simulation_phase3a.py`
- `added`: `tests/test_spectrum_gui_phase1.py`
- `modified`: `tests/test_spectrum_processing.py`
- `added`: `tests/test_spectrum_service.py`
- `added`: `tests/test_spectrum_worker_phase4a.py`
- `modified`: `tests/test_timestamp_stream.py`
- `added`: `uv.lock`
- `added`: `vendor/Cryostation/BakeOut.py`
- `added`: `vendor/Cryostation/BakeOutPurge.py`
- `added`: `vendor/Cryostation/Commands.py`
- `added`: `vendor/Cryostation/Common.py`
- `added`: `vendor/Cryostation/CooldownStepUp.py`
- `added`: `vendor/Cryostation/CryostationComm.py`
- `added`: `vendor/Cryostation/EntryConditionsMet.py`
- `added`: `vendor/Cryostation/LeakTest.py`
- `added`: `vendor/Cryostation/Purge.py`
- `added`: `vendor/IDQ/Examples/Python/Coincidence_counters_acquisition/coincidence_counters_acquisition.py`
- `added`: `vendor/IDQ/Examples/Python/Histogram_acquisition/histogram_acquisition.py`
- `added`: `vendor/IDQ/Examples/Python/Histogram_acquisition_filtred/histogram_acquisition_filtred.py`
- `added`: `vendor/IDQ/Examples/Python/Inputs_status/inputs_status.py`
- `added`: `vendor/IDQ/Examples/Python/Precise_counters_acquisition_over_time/long_precise_input_counters_acquisition.py`
- `added`: `vendor/IDQ/Examples/Python/Precise_counters_acquisition_over_time/precise_coincidence_counters_acquisition.py`
- `added`: `vendor/IDQ/Examples/Python/Precise_counters_acquisition_over_time/precise_input_counters_acquisition.py`
- `added`: `vendor/IDQ/Examples/Python/Read_binary_timestamps/read_binary_timestamps.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition/timestamps_acquisition.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/.gitignore`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/README.txt`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/config.json`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/multi_tc_acquisition/__init__.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/multi_tc_acquisition/acquisition.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/multi_tc_acquisition/config.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/multi_tc_acquisition/config_schema.json`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/multi_tc_acquisition/connect.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/multi_tc_acquisition/const.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/multi_tc_acquisition/exceptions.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/multi_tc_acquisition/setup.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/multi_tc_acquisition/utils.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_multi_tc/timestamp_acquisition_multi_tc.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_stream/timestamps_acquisition_stream.py`
- `added`: `vendor/IDQ/Examples/Python/Timestamp_acquisition_sync_stream/timestamps_acquisition_sync_stream.py`
- `added`: `vendor/IDQ/Examples/Python/utils/acquisitions/__init__.py`
- `added`: `vendor/IDQ/Examples/Python/utils/acquisitions/coincidences.py`
- `added`: `vendor/IDQ/Examples/Python/utils/acquisitions/counts_over_time.py`
- `added`: `vendor/IDQ/Examples/Python/utils/acquisitions/histograms.py`
- `added`: `vendor/IDQ/Examples/Python/utils/acquisitions/streams.py`
- `added`: `vendor/IDQ/Examples/Python/utils/acquisitions/timestamps.py`
- `added`: `vendor/IDQ/Examples/Python/utils/common.py`
- `added`: `vendor/IDQ/Examples/Python/utils/consts.py`
- `added`: `vendor/IDQ/Examples/Python/utils/plot.py`
- `added`: `vendor/IDQ/Examples/SCPI/blank.txt`
- `added`: `vendor/IDQ/Examples/SCPI/coincidence_filter_on_board.txt`
- `added`: `vendor/IDQ/Examples/SCPI/deadtime.txt`
- `added`: `vendor/IDQ/Examples/SCPI/default_config.txt`
- `added`: `vendor/IDQ/Examples/SCPI/synchronized_generators.txt`
- `added`: `vendor/IDQ/Examples/SCPI/tc_as_delay_generator_for_input1.txt`
- `added`: `vendor/IDQ/Examples/SCPI/tc_as_high_resolution_histogram.txt`
- `added`: `vendor/IDQ/Examples/SCPI/tc_as_trigged_pulse_train_generator.txt`

## Exact audit installer delta

- M `docs/README.md`
- M `docs/ai-handover.md`
- M `docs/architecture.md`
- M `docs/commands.md`
- A `docs/comparative-audit.md`
- M `docs/development-conventions.md`
- M `docs/future-refactoring.md`
- M `docs/horiba-alignment.md`
- M `docs/next-recommendations.md`
- M `docs/refactor-notes.md`
- M `docs/refactor-roadmap.md`
- M `docs/session-foundation.md`
- M `docs/shared-map-backend.md`
- M `docs/spectrum-refactor.md`
- M `src/labtools/acquisition/alignment_spectrum.py`
- A `src/labtools/config/horiba_presets.py`
- M `src/labtools/devices/horiba_spectrometer.py`
- M `src/labtools/gui/alignment_gui_horiba.py`
- M `src/labtools/runtime/idq_count_service.py`
- M `src/labtools/runtime/spectrum_backend.py`
- M `src/labtools/runtime/spectrum_worker.py`
- M `src/labtools/simulation/shared_map.py`
- M `src/labtools/simulation/spectrum.py`
- M `tests/test_alignment_gui.py`
- A `tests/test_comparative_audit.py`
