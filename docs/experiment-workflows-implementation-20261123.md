# Experiment workflow implementation checkpoint, 2026-11-23

## Baseline and acceptance

Inspected the supplied 411-file snapshot, with every decoded file size/hash verified.
The manifest/current-state agree on clean feature/unified-gui-alignment HEAD
2dd0661cfd52938bf7f2c76d5f14c93a3110b38d. There is no live Windows .git checkout in
this execution environment; the updater captures/checks the real checkout before
writing. The supplied Windows log reports 630 passed in 74.58 s and Ruff success.
User-reported lab-PC acceptance is recorded separately, including the two clipping
issues. No per-device evidence or new connected pass has been invented.

## Implementation

- New native-free AnnealProgram generates exact-endpoint linear/log dose schedules,
  single points, uniform arrays, serpentine order and pass repetition; checks finite
  values, one-point ambiguity, plan size and the existing total dwell/settle budget.
- New program runner validates all doses against source/local configuration before
  device I/O, then reuses the accepted complete one-point acquisition for each dose.
  This intentionally adds stage/connection overhead between doses. No flat profile
  migration, limit change, shutter-timing change or automatic laser-ON was made.
- Shared SpectrumWorker gains a trusted composed-operation submission method. The
  unified cube holds one configured spectrum operation across the complete grid;
  mirror/native spectrum calls remain on the same owning worker thread/loop.
- Batch holds the union of existing workspace resources for a whole program/cube/
  sequence. Explicit context-local step borrowing is checked against the live lease;
  unrelated threads and panels cannot inherit permission. No resource gap between
  anneal and measurement steps. Existing standalone ownership tests still pass.
- Sequence order is N anneal programs, M measurements, repeated C cycles. Settings
  snapshot, unique outputs and atomic JSON journals; cooperative cancellation and
  active-close integration. Return-stage is required before sequence measurement.
- Spectrum sequence outputs are wavelength/intensity NPZ using no dark subtraction
  in this batch; the separate Spectrum tab's cached-dark and CSV/PNG choices are not
  reused. Cubes have their own explicit dark selector. Intensity maps retain existing
  output format. No arbitrary sequence scripting, resume or automatic power changes.
- Three new operator tabs use the existing Studio layout, scrollable controls and
  wheel protection. Cube final/partial image supports pixel spectrum selection.
  Workspace export/import/startup settings include the new controls.
- Camera forms wrap/expand; map margins use measured Y tick/label width and shrink
  the data area instead of the margin at narrow widths.

## Observed validation

Linux, Python 3.12, offscreen Qt, supplied source snapshot plus this implementation:

- Ruff check --fix on all changed Python: passed.
- Final targeted regression selection: **764 passed, 389 warnings in 153.13 s**.
  The 49-module selection is the preceding all-hardware/GUI/ownership/lifecycle
  selection plus existing hyperspectral modules and the two new test modules.
- New modules contain 28 passing tests covering dose endpoints/order/invalid inputs,
  budget checks, program execution, all three sequence measurement paths and repeats,
  failure abort, cancellation/partial cube, unrelated-thread refusal, fake-real cube
  connection count/thread/home, actual GUI runs, settings round-trip, Stop all/active
  close, resource conflicts, camera wrapping and narrow-map label bounds.
- One existing exact-tab-order assertion was updated to require all three new tabs;
  no test was deleted, skipped, relaxed to a subset or had an existing assertion removed.
- Fake-real cube uses injected transport contracts, not actual HORIBA/LabJack devices.
- Existing warnings are Matplotlib/pyparsing deprecations. No skips in this selection.

Windows validation of the NEW batch: NOT RUN here.
Connected acceptance of the NEW batch: NOT RUN here.
Windows DPI/font clipping correction: requires operator confirmation.
Long powered repeats, every dark mode and every native failure mode: not physically tested.
The previous user-reported baseline pass remains valid within its reported scope.

## Apply and validate on the development PC

Download install_experiment_workflows_20261123.py into C:\Users\mbcx4db7\Downloads.
Close Labtools, then run:

```powershell
Set-Location "C:\Dev\labtools"
py "C:\Users\mbcx4db7\Downloads\install_experiment_workflows_20261123.py" --repo "C:\Dev\labtools" --validate
if ($LASTEXITCODE -ne 0) { throw "Experiment update or Windows validation failed" }
uv run --no-sync labtools native-workspace-gui --manifest "examples\workspace\working-lab\candidate.json" --simulate
```

The updater checks HEAD and inspected source/target hashes, backs up originals,
provides guarded rollback, runs no dependency installation and opens no real devices.
It prints the Windows validation log path. --check is read-only; --validate-only
checks installed payloads and reruns the same offline validation. --print-paths emits
only the exact delivery paths for staging. The backup/validation directory is ignored.
Do not overwrite a target conflict or bypass the source guard; inspect a fresh export.

After Windows tests and a short simulation rehearsal succeed:

```powershell
Set-Location "C:\Dev\labtools"
$paths = @(py "C:\Users\mbcx4db7\Downloads\install_experiment_workflows_20261123.py" --print-paths)
if ($LASTEXITCODE -ne 0) { throw "Cannot obtain exact delivery paths" }
git add -- $paths
if ($LASTEXITCODE -ne 0) { throw "Git staging failed" }
git diff --cached --stat
git commit -m "Add anneal dose programs, unified hyperspectral maps and repeat sequences"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed" }
git push
git rev-parse HEAD
git status --short
```

Review staged scope before commit if other work was already staged. No commit/push
has been performed by the assistant. Transfer/pull this exact revision to the lab PC
before connected checks. Launch with the existing reviewed local Annealing profile:

```powershell
uv run --no-sync labtools native-workspace-gui --manifest "examples\workspace\working-lab\candidate.json" --hardware
```

Retain the existing explicit --anneal-profile argument if that is how the reviewed
profile is selected on the lab PC. No replacement profile is generated or approved.

## Next bounded continuation prompt

Continue from the applied experiment-workflows implementation based on 2dd0661.
Read docs/experiment-workflows.md, docs/unified-gui-lab-acceptance-20261123.md and this
implementation note. Inspect actual Git HEAD/status, the updater's Windows validation
log and current source before editing. The preceding unified all-hardware baseline
has user-reported lab-PC acceptance with two presentation issues; do not erase that
pass or extend it to new features. The delivered Linux selection passed 764 tests;
new Windows/connected acceptance is pending.

Rehearse the actual GUI in simulation: one point at X start/Y start; a small linear
ramp; a strictly positive logarithmic ramp including descending endpoints; inspect
Preview and program.json; a 2x2 hyperspectral cube and selected pixel spectrum;
Workspace settings export/import/startup restore; two-cycle sequences for Spectrum,
Intensity map and Hyperspectral with separate phase counts; Stop all and active
close. Confirm no later step starts after cancellation/failure and all leases release.
Confirm the camera boxes and narrow map Y-axis on Windows.

Then use the exact committed source revision on the lab PC with the existing reviewed
flat Annealing profile. Record small single-point/ramp jobs, cube connect/acquire/home/
disconnect, and one small anneal-then-measure sequence for each measurement separately.
Keep laser Connect/readback separate from intentional Output ON/OFF. No automatic
power change is implemented. Verify saved coordinates/dwells/masks/journals, stage
return before measurement, Stop and active-close cleanup. Mark untested items honestly.
Fix only demonstrated failures, without widening limits, weakening tests, migrating
the profile, redesigning device discovery or adding speculative feature batches.
Deliver exact validation evidence, Git staging/commit commands and the next bounded
continuation prompt at the completed checkpoint.
