# Optional output, retained-run saving and compact Annealing, 2026-11-23

## Inspected baseline

The supplied 17:14:57 export is clean feature/unified-gui-alignment HEAD
5c4c8eaaf9b403957675038c7b1ddf6f32e1393f. All 422 decoded entries were verified
against their declared sizes and SHA-256 hashes. No previous patch was reconstructed.
This updater applies only to that inspected source state (or its already-applied
payloads). No user checkout, Git history or hardware was changed by this delivery.

## Operator behaviour

Automatic experiment output is optional throughout the unified experiment workflows:

- Hyperspectral: new Save results to disk checkbox. Saving off passes no archive
  path, creates no cube-output directory, and retains the complete/stopped cube.
- Intensity map: existing Save completed datasets and plot now means no run files
  when unchecked in the unified GUI, including no checkpoints/metadata directory.
  It uses the explicit memory_only path already introduced for sequences. Standalone
  map save_results/checkpoint semantics are unchanged. Resume is not a memory-only
  operation. A completed/stopped map is retained with counts, rates, axes, mask,
  timestamps, session IDs and the original settings.
- Spectrum: existing Save CSV and Save PNG choices are optional; with both unchecked
  the existing companion NPZ is also not automatically written. A new Save results
  action exports the retained SpectrumResult, including settings/dark provenance.
- Annealing: Save results to disk is the existing save_run_log choice. Uniform scans
  retain their configuration, available progress and final result. Single/ramp plans
  no longer create program.json when saving is unchecked; they retain the dose plan,
  per-point settings/results and completion status. Requested dwell is not a measured
  physical shutter-open duration. Throttled progress does not invent missing timestamps.
- Sequences: Save results to disk remains optional. The returned run now retains ALL
  completed/stopped step results, including the baseline and each later measurement,
  rather than only the last displayed result. Disk journals exclude the in-memory
  result objects. Save results after the run exports the entire retained sequence.

Camera dark capture/load/save is already explicit and remains unchanged. Alignment
has no automatic experiment-output folder; its stream remains a live preview, not a
new recorded time-series workflow. Workspace settings/validation logs are separate
from experiment run output and retain their existing explicit behaviour.

Save results is enabled after cleanup when a retained result exists. It performs no
hardware calls and no reacquisition. It writes a unique directory containing:

- run.json: schema/version, original settings, result types, statuses, step order and
  array references; sequence cycle 0/baseline remains distinct.
- arrays.npz: numeric arrays only, readable with numpy.load(..., allow_pickle=False).
- README.txt: format and no-reacquisition note.

This retained export is a general data/provenance bundle, not the existing cube
archive schema or a promise of automatic CSV/PNG generation. Existing automatic
output formats remain unchanged. No new archive loader/UI or run resume is added.
A failed export reports failure, keeps the data in memory and does not overwrite a
previous export. Retry creates another unique folder. Partial failed export folders
are marked when possible. Large exports are synchronous after acquisition cleanup.

Retention is in RAM for the current run. Starting a replacement run or closing the
application can discard unsaved data; Save first. Spectrum retains the last successful
result until another result replaces it. Full sequence retention can use substantial
RAM for large cubes/repeat counts; no unlimited history, disk cache or implicit save
is introduced. Completed/stopped results are covered. On failures, available prior
steps/progress are retained without fabricating a final result for a failed vendor call.

## Layout

Sequence spectrum and intensity-map results use one full plotting grid, not a hidden
second subplot. Spectrum is centred/full-width. Intensity maps preserve equal pixel
aspect and are centred within that area. Hyperspectral retains map/spectrum panels
and pixel selection. The text area shows a concise status/step count instead of a
raw dictionary containing arrays.

Annealing keeps the operational shutter and stage controls, merged into Instruments.
Dose/scan/optional preview are on the left; Instruments and Output are on the right.
Output is outside the left scroll area and visible at the tested 1400x760 window.
The existing stage/shutter callbacks and return-stage policy are preserved. Start,
Stop, estimate and status remain along the bottom. Smaller Windows/DPI layouts still
need operator confirmation; this is not a claim that any arbitrarily small window fits.

## Actual validation

- Regression group A: 341 passed, 317 warnings in 113.93 s.
- Regression group B: 448 passed, 329 warnings in 106.96 s.
- Total in those two non-overlapping completed groups: 789 passed; no failures/skips.
- Thirteen new tests cover no-output acquisition, post-run export without replacing
  retained data, full baseline/cycle retention for all measurement choices, NPZ arrays,
  unique export paths, failed-save retention, full-area plotting, visible Annealing
  output, and both single-point/uniform Annealing retention.
- Ruff check --fix on changed Python and compileall passed.
- After final tooltip/disabled-field refinements, the 13 new tests passed again in
  36.53 s; no acquisition behaviour changed in those final refinements.
- Updater smoke passed: read-only preflight, conflict refusal, exact apply,
  idempotency, guarded rollback, original restoration and source-anchor refusal,
  tested only in a temporary Git checkout with its temporary baseline substituted
  in memory. No user Git checkout/history was changed.
- Actual simulated Qt screenshots were reviewed; no conceptual/generated images.
- No physical devices were connected. New Windows/connected acceptance is pending.

An unchanged standalone hyperspectral lifecycle audit hung in combined Linux runs
under captured output. Its source/test assertions were not changed or removed. It
passed alone with capture disabled, and the complete B selection passed with that
module first and capture disabled. The validation runner preserves all tests and
uses this explicit order/-s mode; no test timeout was extended and no real acquisition
delay added. Failed/timed-out attempts are not counted as passes. Windows must run
its own validation; this environment observation is not a new hardware pass.

The Linux test environment uses Python 3.12/Qt6 offscreen raster with temporary
Chromium ANGLE loader libraries, not shipped hardware drivers. Existing warnings are
Matplotlib/Pyparsing deprecations. Repository dependencies/lock/profile schemas,
hardware limits, laser output defaults and acquisition cleanup policies are unchanged.

## Apply, rehearse and commit

Save install_retained_output_20261123.py in C:/Users/mbcx4db7/Downloads. Close Labtools:

```powershell
Set-Location "C:\Dev\labtools"
py "C:\Users\mbcx4db7\Downloads\install_retained_output_20261123.py" --repo "C:\Dev\labtools" --validate
if ($LASTEXITCODE -ne 0) { throw "Retained-output update or Windows validation failed" }
$env:PYTHONPATH = (Resolve-Path ".\src").Path
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
& ".\.venv\Scripts\python.exe" -m labtools workspace launch "examples\workspace\working-lab\candidate.json" --simulate --simulation-realtime
```

The updater checks target/source hashes and actual HEAD/status, keeps backups,
supports guarded rollback and prints validation logs. It installs no dependencies,
connects no hardware and changes no Git history. Do not replay old installers.
Rehearse saving off then Save results for a small spectrum/map/cube/anneal/sequence.
Check baseline and all sequence measurements in run.json/arrays.npz, not just the
latest plotted result. Confirm Output visible on Annealing and the plot layout.

```powershell
$paths = @(py "C:\Users\mbcx4db7\Downloads\install_retained_output_20261123.py" --print-paths)
if ($LASTEXITCODE -ne 0) { throw "Cannot obtain delivery paths" }
git add -- $paths
if ($LASTEXITCODE -ne 0) { throw "Git staging failed" }
git diff --cached --stat
git commit -m "Add optional output and retained-run exports with compact Annealing layout"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed" }
git push
git rev-parse HEAD
```

Review any previously staged work before committing. Update the lab PC to that exact
hash, retain the existing reviewed local Annealing profile, and use the same module
launch with --hardware for small connected checks. Existing physical interlocks and
optical setup remain required; Stop all is cooperative, not an emergency stop.

## Next bounded continuation prompt

Continue from the applied retained-output/compact-Annealing update. Inspect actual
Git HEAD/status, current source, Windows validation output and this note before
editing. Preserve earlier baseline acceptance; do not extend it to this update.
Rehearse automatic saving off and Save results afterward for Spectrum, intensity map,
hyperspectral, uniform/single/ramp Annealing and baseline-first sequences. Verify no
run files before explicit saving, no reacquisition during export, complete retained
sequence step order/data, completion masks/axes/settings, unique paths, failed-save
retry and the current-run RAM lifetime. Confirm single full-area spectrum/map views,
two-panel cubes/pixel selection, compact Instruments and visible Annealing Output.
Then test small connected jobs at the exact committed revision with the existing
reviewed flat profile and laser policy. Record actual observations, mark untested
items honestly, and fix only demonstrated failures without widening limits, weakening
tests, migrating profiles or adding speculative feature batches. Deliver actual
evidence, exact Git staging/commit commands and the next bounded prompt.
