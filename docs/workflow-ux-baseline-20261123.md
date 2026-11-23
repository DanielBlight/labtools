# Consolidated workflow UX and baseline-first sequences, 2026-11-23

## Source and acceptance

Implemented from the supplied 16:14:05 full-source export, 420 files, individually
size/hash verified. Manifest HEAD is 2dd0661cfd52938bf7f2c76d5f14c93a3110b38d;
the preceding experiment implementation is applied but uncommitted. The updater
accepts this exact dirty snapshot and preserves its prior work. It does not require
reapplying old installers or committing before applying this update.

The user supplied Windows validation of the preceding experiment implementation:
764 passed in 72.47 s, Ruff passed. The subsequent launch error was in the executable
wrapper/incorrect command, not the test run. All launch instructions here use the
verified python -m labtools workspace launch entry point. Existing user-reported
lab-PC baseline acceptance remains recorded in unified-gui-lab-acceptance-20261123.md.
Neither previous pass is extended to these new UI/sequence changes.

## Visible workflow

One Annealing tab contains the mode, shared grid/stage/output controls and shared
Point / first dwell. Single point uses X start/Y start; unused stop/count controls
are disabled without destroying the array settings. Dwell ramp enables Last dwell
and Linear/Logarithmic spacing. Preview point doses expands an optional preview.
One visible Start/Stop pair dispatches the selected mode. Uniform manual scanning
retains the accepted existing uniform acquisition; single/ramp programs retain
per-point shutter/stage cleanup. Sequences use the selected dose plan with the
existing program runner. The internal program object remains registered only for
worker lifecycle/settings compatibility; it is never a second visible tab.

Hyperspectral has independent X/Y start, stop, point counts and mirror settle. It
continues to snapshot Spectrum detector/range/exposure/readout settings. The output
field and Browse occupy full-width form rows with aligned right edges. Spatial
settings are source-limit validated before acquisition and saved in Workspace
preferences/export. Legacy settings without these fields start from source defaults.

Live cube display receives immutable per-pixel spectra and a cumulative integrated
image. The GUI has a lock-protected latest-only mailbox polled on its existing timer;
no widget or canvas is touched from the acquisition thread, no unbounded frame queue
and no whole-cube copy per frame. Unvisited pixels remain NaN. The latest spectrum
updates during acquisition; after completion the full cube supports pixel selection.
Rapid frames may coalesce for display, but the acquisition cube retains every pixel.
This is not a guaranteed display refresh rate or a new real-acquisition delay.

Alignment is a modeless child window opened by Open alignment in Spectrum. There
is no Alignment tab. Closing the popup stops an active stream, waits for its cleanup,
then hides it; reopening reuses the same shared worker and settings. Global Stop all,
resource exclusion, preferences and application close still include the popup.
Closing the popup does not close the application-owned spectrum worker.

Sequences have Measurement, Cycles and optional Save results to disk. The old phase
repeat controls are removed. Legacy phase-count preferences are accepted but ignored;
new saves omit them. Exactly one anneal and one measurement occur per cycle.

Every sequence performs ONE baseline measurement BEFORE the first anneal, then
[anneal, post-anneal measurement] for each cycle. C cycles mean C anneals and C+1
measurements. The baseline uses the same snapshotted measurement request as later
measurements and is recorded as cycle 0 / role baseline. When saving, it has its own
0000-baseline directory. A baseline failure/cancellation prevents the first anneal.
The exclusive union lease covers the baseline and all subsequent phase gaps.

The sequence result view shows the latest spectrum/map/cube. Map/cube measurements
update while running; spectra display when the spectrum operation returns. The last
measurement remains visible during annealing and after completion. The baseline is
therefore visible before the first anneal. No automatic laser ON/current change is
introduced. Spectrum sequences continue to use raw/no-dark NPZ results; cube dark
selection remains explicit. Existing reviewed stage return is required.

With Save results disabled, no sequence/program/point/map/cube run-output directory,
checkpoint, metadata, archive or image is created. Results remain in memory for the
latest-result view. A new explicit memory_only map argument bypasses disk checkpoints
without changing standalone save_results semantics. Resume is refused in memory-only
mode. Application startup preferences and validation logs are separate from run
output and can still be written by their existing explicit mechanisms.

Stop/failure prevents later steps. Cleanup and lease release precede terminal GUI
state. No new instrument-profile schema, limit widening, dependency/lock change,
forced vendor-call interruption, automatic laser output or calibration is included.

## Validation evidence and limits

Two non-overlapping targeted runs passed: 341 tests in 111.69 s and 435 tests in
74.10 s, 776 total, with no failures/skips in those completed runs. The selection
covers the preceding workflow/hardware/ownership/alignment/hyperspectral tests and
12 new tests for baseline order/failure, no-output runs for all measurements, distinct
baseline saving, one visible Annealing page, independent cube grid/output widths,
live data before completion, popup close/reopen and latest sequence results.

After final UI-only single-point/visibility/preview refinements, the affected GUI
selection was rerun: 21 passed in 71.47 s, then the 12 focused UX tests passed in
27.23 s. No old assertion was removed; tab/sequence-order expectations were changed
to the user's requested semantics and small cube tests now set the cube's own grid.
The final collapsed-preview refinement does not change acquisition code. The final
21-test GUI selection passed again in 67.40 s after that refinement.

Updater smoke checks passed in a temporary Git checkout: no-write preflight, target
conflict refusal, exact installed bytes, repeat application, refusal to rollback
later edits, restoration of the supplied snapshot and unchanged-source anchor refusal.
Only the temporary baseline hash was substituted in memory for this test; no user
checkout or Git history was changed.

Ruff check --fix and compileall are included. Actual offscreen Qt screenshots were
reviewed; a hidden-legacy-scroll insertion was caught and corrected, with a visible
mode-control assertion added. Windows fonts/DPI and connected new-workflow acceptance
remain pending. Linux uses Python 3.12/Qt6 offscreen raster; temporary Chromium ANGLE
loader libraries support Qt imports, not shipped drivers. All acquisitions here use
simulation/injected fake transports, never physical devices.

An initial combined run exceeded the container's execution watchdog; no pass was
claimed from it. A split attempt also timed out; the two completed diagnostic runs
above establish the reported results. Test deadlines were not extended, assertions
not weakened, and real-acquisition sleeps not added to address that environment limit.

## Apply and rehearse

Save install_workflow_ux_20261123.py in C:/Users/mbcx4db7/Downloads. Close Labtools:

```powershell
Set-Location "C:\Dev\labtools"
py "C:\Users\mbcx4db7\Downloads\install_workflow_ux_20261123.py" --repo "C:\Dev\labtools" --validate
if ($LASTEXITCODE -ne 0) { throw "Workflow update or Windows validation failed" }
$env:PYTHONPATH = (Resolve-Path ".\src").Path
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
& ".\.venv\Scripts\python.exe" -m labtools workspace launch "examples\workspace\working-lab\candidate.json" --simulate --simulation-realtime
```

The updater checks all targets/source anchors before writing, prints actual HEAD/
status, keeps originals, supports guarded rollback and writes validation logs. It
does not install dependencies, change Git history or connect hardware. --print-paths
includes the previous uncommitted experiment batch AND this update for one coherent
commit. Review staged scope first if unrelated work is already staged.

```powershell
$paths = @(py "C:\Users\mbcx4db7\Downloads\install_workflow_ux_20261123.py" --print-paths)
if ($LASTEXITCODE -ne 0) { throw "Cannot obtain delivery paths" }
git add -- $paths
if ($LASTEXITCODE -ne 0) { throw "Git staging failed" }
git diff --cached --stat
git commit -m "Consolidate annealing, live hyperspectral views and baseline-first sequences"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed" }
git push
git rev-parse HEAD
```

After a short simulation rehearsal, update the lab PC to that exact committed hash
and launch the same module command with --hardware, retaining the existing reviewed
local Annealing profile. Use small jobs first and the existing optical setup/interlocks.
Stop all is cooperative, not an emergency stop. No connected pass is claimed here.

## Next bounded continuation prompt

Continue from the applied consolidated-workflow/baseline-first update. Inspect actual
Git HEAD/status, current source, the Windows validation log and this note before editing.
Preserve the prior reported unified GUI lab-PC pass and the 764-pass Windows experiment
validation; do not extend either to this new checkpoint. Rehearse one visible Annealing
page (uniform/single/ramp), shared dwell and optional dose preview; independent small
cube grids and live completed pixels/latest spectrum; full-width output fields; Alignment
popup Start/Stop/close/reopen and range exclusion; optional-output sequences for all
three measurements. Verify baseline measurement first, then exactly one anneal and
measurement per cycle; C cycles give C anneals/C+1 measurements. Verify baseline failure/
Stop prevents annealing, last results stay displayed, no run files when saving off,
distinct baseline output when saving on, and global Stop/active-close cleanup.
Commit/push only after Windows validation/rehearsal, then test small connected jobs
at that exact hash with the existing reviewed flat profile and laser policy. Record
actual observations separately, mark untested items honestly, and fix only demonstrated
failures without widening limits, weakening tests, migrating profiles or adding speculative
feature batches. Deliver exact evidence, Git commands and the next bounded prompt.
