# Workflow visual polish, 2026-11-24

## Inspected state

The supplied 11:24:35 export contains 432 individually size/SHA256-verified files.
Actual HEAD is 5651ddebe0802978f425beeac890d49ccf341445. The hyperspectral teardown
repair is committed; the mirror/positioned-spectrum update remains applied but
uncommitted (11 modified and four new paths). This updater accepts that exact
snapshot, preserves the prior work and stages neither files nor Git history.
The user clarified that the requested popup cleanup refers to Mirror, not Camera.

## Changes

Only two production GUI files change:

- Hyperspectral/Sequences: the existing acquisition log is hidden by default and
  exposed by a checkable Details button below the compact status. The existing
  plot layout receives the freed space. Output paths/messages remain in the log;
  toggling Details does not clear them. Status and Save results remain available
  with Details collapsed. Existing two-panel cubes/single-panel sequence results,
  live rendering, retained results and saving behaviour are unchanged.
- Mirror popup: long operational text moved to a tooltip on the short visible
  note, Commanded voltages, not readback. The empty log panel stays hidden.
  Home remains above a centred equal-width Move X/Y and Stop row. Status still
  reports last command/errors. Opening/closing/field edits still send no movement.
  No separate Move X/Move Y commands are added; the existing combined X/Y command
  and source limits remain unchanged. The popup is compact with modest margins.
- Mirrors header action: copies Camera's teal stylesheet (including hover,
  pressed/disabled rules), font/cursor and fixed dimensions. The two buttons use
  the same size, chosen from their styled size hints and existing minimum size.
  Camera preview/controls are otherwise untouched.

No runtime, instrument transport, thread teardown, sequence order, calibration,
profile, hardware limit, laser/shutter policy, dependency or lockfile change.
No automatic output, extra hardware operation or forced interruption is added.
Details expansion is local presentation state, not a new saved preference.

## Observed validation

Three non-overlapping selections completed in Linux/offscreen Qt:

- GUI/mirror/experiment panels: 30 passed, 278 warnings in 88.32 s.
- Workflow/retained-output/runtime regressions: 44 passed, 265 warnings in 75.63 s.
- Original hyperspectral worker/lifecycle/reaping audits: 21 passed, 13 warnings
  in 10.07 s. The committed teardown repair is unchanged.
- Total: 95 passed; no failures/skips in those completed runs.
- Five new tests check default collapsed logs, working Details with retained text,
  reclaimed plot height, exact Camera/Mirrors dimensions/style parity, compact
  centred mirror actions/no implicit movement, and cube status/save availability.
- Ruff check --fix and compileall passed. Actual simulated Qt screenshots reviewed.
- Updater smoke passed: no-write preflight, target/source conflict refusal, exact
  apply, idempotency, guarded rollback, original restoration and mirror-runtime
  preservation. Tested in a temporary Git checkout with only HEAD substituted in
  memory. No user Git checkout/history changed.

These are simulation/injected transport tests, not physical hardware acceptance.
New Windows visual/automated acceptance remains pending. Earlier user-reported
working behaviour is not extended to a new connected pass. Existing Pyparsing/
Matplotlib warnings are unchanged. Linux uses Python3.12/Qt6 offscreen raster with
temporary Chromium ANGLE loader shims, not shipped device drivers. No test timeout
was extended and no existing assertion was removed.

## Apply and rehearse

Save install_workflow_visual_polish_20261124.py in Downloads. Close Labtools:

```powershell
Set-Location "C:\Dev\labtools"
py "C:\Users\mbcx4db7\Downloads\install_workflow_visual_polish_20261124.py" --repo "C:\Dev\labtools" --validate
if ($LASTEXITCODE -ne 0) { throw "Visual polish update or Windows validation failed" }
$env:PYTHONPATH = (Resolve-Path ".\src").Path
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
& ".\.venv\Scripts\python.exe" -m labtools workspace launch "examples\workspace\working-lab\candidate.json" --simulate --simulation-realtime
```

The updater checks HEAD and source hashes before writing, prints actual status,
keeps backups, supports guarded rollback and logs validation. It does not install
dependencies, connect hardware or mutate Git. Do not replay older installers:
their preflight hashes correctly describe older source states. The current updater
runs the three targeted selections above without changing test order/deadlines.

Rehearse Hyperspectral and Sequences with Details closed/open, output path text,
Save results, plot resizing, and Camera/Mirrors parity at your Windows DPI. Check
Mirror popup Move/Home/Stop, short note/tooltips, status, close/reopen and no empty
panel. Keep the existing reviewed optical setup for later connected checks.

## Commit the complete pending feature

The manifest shows the mirror feature is still uncommitted. --print-paths includes
that prior feature AND this polish so the commit does not omit its runtime/tests.
It excludes unrelated paths and the already-committed teardown repair. Review any
previously staged work before committing:

```powershell
$paths = @(py "C:\Users\mbcx4db7\Downloads\install_workflow_visual_polish_20261124.py" --print-paths)
if ($LASTEXITCODE -ne 0) { throw "Cannot obtain delivery paths" }
git add -- $paths
if ($LASTEXITCODE -ne 0) { throw "Git staging failed" }
git diff --cached --stat
git commit -m "Complete workspace mirror positioning and compact workflow presentation"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed" }
git push
git rev-parse HEAD
git status --short
```

## Next bounded continuation prompt

Continue from the applied visual-polish update over committed teardown repair and
pending mirror feature. Inspect actual HEAD/status, current source and Windows
validation log before editing. Preserve runtime/teardown/positioned-spectrum code.
Verify collapsed Details on Hyperspectral/Sequences removes the bottom white box,
expands plots, retains messages/output paths and does not hide status/Save results.
Check Camera/Mirrors style/dimension parity at Windows DPI, compact Mirror popup,
centred combined Move X/Y and Stop, Home above, short note/tooltips and no empty log.
Rehearse explicit movement/close/reopen, overlap refusal, baseline-first Spectrum
position/settle, optional output/save afterward and active-close cleanup. Commit
both pending mirror feature and polish after validation/rehearsal; do not omit the
prior untracked runtime/tests. Record actual automated/visual/connected evidence
separately. Fix only demonstrated failures, with no limit/profile changes, timeout
extensions, weakened tests or speculative feature batches. Deliver exact Git
commands and the next bounded prompt.
