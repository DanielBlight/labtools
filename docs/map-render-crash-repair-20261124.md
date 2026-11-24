# Saved-map rendering and save-button lifetime repair, 2026-11-24

## Observed failure and scope

The supplied Windows log shows the visual-polish installer applied all four paths
and Ruff passed. The first 24 tests passed, then Windows raised a fatal access
violation during the saved Intensity map sequence test. The acquisition worker
was inside plot_intensity_map -> savefig -> Agg/mathtext glyph rendering; the GUI
thread was processing a retained-run save-button timer callback. This is not the
previous QThread teardown hang and not an expected fault-injection traceback.
The visual-polish Windows validation did NOT pass. Do not commit it as accepted.

The stack identifies concurrent native plotting and GUI callback activity; it
cannot by itself prove the exact native memory fault. Matplotlib documents that
it is not thread-safe. Earlier Linux mixed-GUI segfaults had also been observed
in the save-button lambda; treating those as merely environmental was insufficient.
This bounded repair addresses both demonstrated paths, not only test ordering.

Base: the supplied 11:24:35 export at HEAD
5651ddebe0802978f425beeac890d49ccf341445 plus the exact four visual-polish payloads
which the user's successful preflight/apply/Ruff output confirms were installed.
No newer unobserved edits are assumed. The installer hash-checks this expected
state and refuses conflicts. It does not replace the visual-polish, mirror,
positioned-spectrum or committed hyperspectral teardown implementation.

## Repair

1. Acquisition PNG rendering moves out of the GUI/acquisition process into one
   lazy, serialized Agg-only Python child. The child uses the SAME interpreter
   and source package root, imports no Qt/pyplot/hardware, receives only numeric
   arrays and a title through temporary NPZ files (allow_pickle=False), and writes
   the same summed_intensity_map.png through the existing plotting helper.
   Reusing the isolated child amortizes font/import startup across sequence maps.
   No GUI rendering lock is held and no acquisition is repeated.
2. Existing CSV/NPZ outputs are written before PNG rendering. PNG is rendered to
   a temporary sibling folder and atomically moved to the target on success.
   A failed renderer cannot replace an earlier PNG with a partial file. Failures
   remain visible; the sequence does not silently continue after a failed export.
   Temporary payloads are cleaned on normal success/error. Saving off still uses
   the existing memory-only path and creates no renderer/run files.
3. The renderer is lazy, single-request-at-a-time, reaped on error/normal interpreter
   shutdown, and restarted on a later request after child exit. A 120 s response
   bound kills/reaps ONLY this rendering child on timeout. This is a new export
   resource bound, not an extension of any test/acquisition deadline. Stop/close
   remain cooperative and can wait for an in-progress export to complete/fail.
   The child holds no instrument handles; idle it only waits for requests. Windows
   uses CREATE_NO_WINDOW to avoid a console flash. No network or external service.
4. Save-button availability refresh is now a QObject-owned @pyqtSlot rather than
   an anonymous timer lambda. Qt can disconnect the receiver with its button;
   refresh stops after workspace closure. Existing busy/retention checks, explicit
   save action and output data format remain unchanged. No UI redesign added.

No profile, hardware limits, laser/shutter policy, sequence target/order, numeric
acquisition algorithm, dependency or lockfile change. Standalone explicit plotting
helpers remain unchanged; this patch isolates the automatic acquisition PNG path.

## Actual validation

Completed final Linux/offscreen selections, non-overlapping:

- Original failing selection in the SAME order, existing assertions/deadlines:
  30 passed, 253 warnings in 84.02 s.
- Workflow/retained-output/runtime selection:
  44 passed, 241 warnings in 72.18 s.
- Export isolation plus existing worker-export and hyperspectral lifecycle tests:
  31 passed, 185 warnings in 31.17 s.
- Total: 105 passed, no skips/failures in those completed runs.
- Nine new tests cover no parent savefig call, actual child PNG, NaN numeric data,
  live GUI drawing while a worker saves a map, failed/missing export preservation,
  child reuse/restart, protocol EOF/timeout reaping and save-timer shutdown.
- Ruff check --fix and compileall passed. Updater smoke passed in a temporary
  Git checkout: no-write preflight, target/source conflict refusal, exact apply,
  idempotency, guarded rollback, original restoration and preservation of prior
  mirror runtime. Only HEAD was substituted in memory for that smoke test; no
  user Git checkout/history changed.

Development attempts are not counted as passes: the first per-export fresh-child
prototype exceeded the existing 8 s sequence test deadline, so it was replaced
with the serialized persistent child rather than extending the deadline. The
broader retention run then reproduced the save-timer segfault, prompting the
Qt-owned refresh fix; the same selection subsequently passed. No existing test
was removed, reordered to hide a failure, skipped or given a longer deadline.
Early new-test harness errors (missing lease and monkeypatching subprocess.run
before NumPy testing import) were corrected without weakening production checks.

New Windows and physical connected acceptance remain pending. The 105 local tests
are simulation/injected transport tests, not a physical-device pass. Linux uses
Python3.12/Qt6 offscreen raster with temporary ANGLE loader shims; existing warnings
are Matplotlib/Pyparsing. Windows is the required next confirmation.

## Apply and validate

The crash has already ended validation. Leave the applied layout changes in place;
do not rerun or roll back the old polish installer. Close Labtools, save
install_map_render_repair_20261124.py in Downloads, then run:

```powershell
Set-Location "C:\Dev\labtools"
py "C:\Users\mbcx4db7\Downloads\install_map_render_repair_20261124.py" --repo "C:\Dev\labtools" --validate
if ($LASTEXITCODE -ne 0) { throw "Map rendering repair or Windows validation failed" }
```

This updater preserves prior work, backs up originals, supports guarded rollback,
prints actual HEAD/status and logs command exits. No dependencies installed,
hardware opened or Git history changed. It reruns the original 30-test selection
first, then retention/runtime and export/teardown selections. Old installers'
--validate-only anchor hashes will correctly refuse this new acquisition source;
use this validation entry point instead of bypassing their guards.

After validation, normal simulation:

```powershell
$env:PYTHONPATH = (Resolve-Path ".\src").Path
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
& ".\.venv\Scripts\python.exe" -m labtools workspace launch "examples\workspace\working-lab\candidate.json" --simulate --simulation-realtime
```

Rehearse a small saved intensity map sequence with live plots and inspect baseline
and post-anneal PNG/CSV/NPZ files. Recheck saving off then Save results, collapsed
Details, Camera/Mirrors parity and compact popup. No new connected acceptance is
inferred; retain the reviewed optical setup/local profile for later physical tests.

## Commit the complete pending feature and repair

--print-paths includes the still-pending mirror feature, applied visual polish and
this repair, excluding unrelated work and already-committed teardown repair.
Review previously staged scope before committing:

```powershell
$paths = @(py "C:\Users\mbcx4db7\Downloads\install_map_render_repair_20261124.py" --print-paths)
if ($LASTEXITCODE -ne 0) { throw "Cannot obtain delivery paths" }
git add -- $paths
if ($LASTEXITCODE -ne 0) { throw "Git staging failed" }
git diff --cached --stat
git commit -m "Complete mirror workflow polish and isolate saved-map rendering"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed" }
git push
git rev-parse HEAD
git status --short
```

## Next bounded continuation prompt

Continue from the applied map-render/save-button lifetime repair over the pending
mirror feature and visual polish. Inspect actual HEAD/status, current source and
complete Windows validation log. Do not record the prior access-violation run as
passed. Confirm the original 30-test selection completes unchanged, including
saved intensity-map sequences, followed by retention/runtime/export/teardown tests.
Rehearse saved baseline/post-anneal map PNG/CSV/NPZ while live GUI plots update,
saving off then Save results, renderer error visibility and no reacquisition.
Preserve collapsed Details, matching Camera/Mirrors actions, compact popup,
positioned Spectrum steps, shared exclusion and committed teardown repair. Verify
save availability stops after workspace close and renderer child cleanup/reuse.
Commit intended pending mirror/polish/repair scope only after Windows validation
and rehearsal. Record automated, visual and connected evidence separately; use
small connected checks at the exact committed revision with the reviewed profile/
laser policy. If a native crash remains, preserve the complete stack/log and source
before further edits; do not hide it by reordering tests, disabling PNG output,
extending deadlines or weakening assertions. Deliver exact Git commands and the
next bounded continuation prompt.
