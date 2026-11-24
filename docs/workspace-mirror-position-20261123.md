# Workspace mirror popup and sequence spectrum coordinates, 2026-11-23

## Inspected source and acceptance

The supplied clean export is feature/unified-gui-alignment HEAD
2f0312d0cbdc3434281d9eed3f816430de2f3e42. All 426 decoded file entries were checked
against declared sizes and SHA-256 hashes. The preceding optional-output update is
committed. The user reports its normal GUI looks good; the supplied prior Windows
validation ended with 448 passed in 52.44 s and Targeted validation passed. Record
that as preceding automated/visual acceptance, not a connected pass for this feature.

## Mirror popup

Mirrors is placed immediately after Camera in the header. It opens a modeless child
window with X/Y voltage controls, Move X/Y, Move to configured home, Stop and last
command status. The earlier mirror_voltage_gui/mirror_controller implementation was
inspected. This popup retains the same voltage convention but does not reuse its
independent hard-coded +/-10 V/DIO2 native connection. Instead it uses the workspace's
reviewed mirror DIO/home values and the intersection of source/map voltage limits.
No standalone GUI behaviour, profile schema or approved limits were changed.

Opening, closing or changing a field sends no movement. Move/Home explicitly reserve
the existing optical workflow resources, open the LabJack/mirror on a background
worker, send the target and close the connection WITHOUT an implicit home move.
There is no persistent Connect session that blocks later acquisition. The last target
remains commanded after the connection closes. A subsequent scan/anneal can move or
home the mirror according to its existing acquisition policy. Values/status are
commanded voltages, NOT position or voltage readback. No new physical calibration,
closed-loop positioning, zero command or laser/shutter/gate output change is added.

Only explicit --simulate and --hardware modes expose this popup. HORIBA-only and
default-disabled modes remain unchanged. Move/Home are refused during overlapping
spectrum/alignment/map/anneal/sequence work by the existing shared resource registry.
Global Stop all and active application close include manual-command completion and
connection cleanup. Stop cannot undo a DAC write or forcibly interrupt a vendor call;
if the move has already been sent, cleanup still runs. Closing an idle popup simply
hides it; reopening is usable without rebuilding a native connection. A native move/
cleanup failure faults further hardware work until application teardown, preserving
error context. The reviewed beam setup/physical interlocks remain required.

## Sequence Spectrum position

When Measurement is Spectrum, a Spectrum position card shows X (V), Y (V) and Mirror
settle (s). It is hidden for Intensity map/Hyperspectral, whose own grids remain
unchanged. Defaults are configured home and source map settle. Settings export/import
and startup restore include these values. Legacy preferences without them use defaults.
Changing controls during a run affects only the next snapshotted run.

For every spectrum step, including the pre-anneal baseline, the sequence:

1. Holds its existing union lease, validates the target against source limits.
2. Opens the mirror and moves to the selected X/Y.
3. Waits the specified settle time, checking cancellation during the wait.
4. Acquires the spectrum through the SAME application-owned SpectrumWorker.
5. Attempts configured mirror home and closes the LabJack before the next step.

Mirror and native spectrum handles are created/called/cleaned on the spectrum owning
thread/loop. No second HORIBA worker is introduced. A position/settle/acquisition
failure or Stop prevents the next anneal/measurement. A cancelled settle homes and
skips spectrum acquisition. The baseline is still cycle 0; C cycles still mean C
anneals and C+1 measurements. No automatic laser ON/current change is made.

The target/settle tuple is stored in sequence.json and the retained run settings, and
attached to retained Spectrum steps. Save results afterward therefore preserves the
requested position without reacquisition. The tuple is a command request, not proof
of measured physical location. The public internal runner retains spectrum_position=None
for old callers; the unified GUI always supplies its selected target for Spectrum.

## Observed validation

- Regression group A: 341 passed, 317 warnings in 118.31 s.
- Regression group B: 475 passed, 345 warnings in 127.89 s.
- Total across the two non-overlapping completed selections: 816 passed; no skips.
- Sixteen new tests cover finite/source-limit validation before I/O, lease refusal,
  no implicit manual home, popup placement/open/close/reopen, settings round-trip,
  positioned baseline/cycle metadata, cancellation before move/during settle,
  Stop-all/active-close handling, failure abort and injected-real single-thread
  mirror-before-spectrum/home-after ordering. Existing standalone mirror tests remain.
- Final UI-only popup sizing/card-order refinement: focused 16 tests rerun, passed
  in 14.56 s. The final removal of the unused splitter panel is presentation-only.
- Final popup sizing after removing the unused splitter pane: 16 tests passed
  again in 14.55 s. No acquisition behaviour changed.
- Updater smoke passed: read-only preflight, conflict refusal, exact installed bytes,
  idempotency, guarded rollback, original restoration and unchanged-source refusal.
  Tested in a temporary Git checkout only, with its baseline substituted in memory.
- Ruff check --fix and compileall passed; actual offscreen Qt screenshots
  reviewed. No conceptual image generation or physical hardware operation used.

New Windows automated/visual and connected acceptance: NOT RUN here. Fake-real
transport contracts are not actual LabJack/HORIBA acceptance. Physical beam position,
DAC latency, powered movement and every native failure mode remain untested.
Linux uses Python3.12/Qt6 offscreen raster with temporary Chromium ANGLE loader
libraries, not shipped device drivers. Existing warnings are Matplotlib/Pyparsing.
No dependency/lock changes, limits widened, tests removed or timeout relaxations.

## Apply, rehearse and commit

Save install_workspace_mirror_20261123.py in C:/Users/mbcx4db7/Downloads. Close Labtools:

```powershell
Set-Location "C:\Dev\labtools"
py "C:\Users\mbcx4db7\Downloads\install_workspace_mirror_20261123.py" --repo "C:\Dev\labtools" --validate
if ($LASTEXITCODE -ne 0) { throw "Mirror update or Windows validation failed" }
$env:PYTHONPATH = (Resolve-Path ".\src").Path
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
& ".\.venv\Scripts\python.exe" -m labtools workspace launch "examples\workspace\working-lab\candidate.json" --simulate --simulation-realtime
```

The updater checks actual HEAD/status and inspected source/target hashes before
writing, keeps backups, supports guarded rollback and prints validation logs. No
dependency installation, native device connection or Git mutation. Do not replay
previous installers. Rehearse Move/Home, popup close/reopen, overlap refusal and a
small baseline-first Spectrum sequence at a non-home target. Confirm retained export
includes the selected target. Then commit/push the exact tested revision:

```powershell
$paths = @(py "C:\Users\mbcx4db7\Downloads\install_workspace_mirror_20261123.py" --print-paths)
if ($LASTEXITCODE -ne 0) { throw "Cannot obtain delivery paths" }
git add -- $paths
if ($LASTEXITCODE -ne 0) { throw "Git staging failed" }
git diff --cached --stat
git commit -m "Add workspace mirror popup and positioned sequence spectra"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed" }
git push
git rev-parse HEAD
```

Review any previously staged work. Update the lab PC to that exact hash and use the
same module launch with --hardware, retaining the existing reviewed local Annealing
profile. Use small commands under the reviewed optical setup. Stop all is cooperative,
not an emergency stop. Do not infer connected acceptance from simulation.

## Next bounded continuation prompt

Continue from the applied workspace-mirror/positioned-spectrum update. Inspect actual
Git HEAD/status, current source, Windows validation log and this note before editing.
Preserve earlier automated/visual acceptance; do not extend it to these new controls.
Rehearse Mirrors next to Camera, explicit Move/Home, no movement on open/close/field
edits, close/reopen, source-limit refusal and exclusion during spectrum/alignment/
map/anneal/sequence work. Verify Stop all and active-close wait for command cleanup.
For Spectrum sequences set a non-home X/Y/settle, verify baseline and every later
spectrum use that snapshotted target, mirror home after each, cancellation/failure
prevents the next step, and target metadata survives Save results. Map/cube grids
remain independent. Commit/push after Windows validation/rehearsal, then perform
small connected checks at the exact hash with the existing reviewed profile/laser
policy. Record actual observations, mark untested items honestly, and fix only
demonstrated failures without widening limits, weakening tests, migrating profiles
or adding speculative feature batches. Deliver actual evidence, exact Git commands
and the next bounded continuation prompt.
