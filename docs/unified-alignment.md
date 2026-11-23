# Unified alignment and real HORIBA operation

## All-hardware workspace extension, 2026-11-23

The shared Spectrum/Alignment worker is unchanged in the new explicit `--hardware`
mode, which additionally binds map, Annealing and laser. The `--hardware-spectrum`
mode below still leaves those workflows gated. Workspace now supports portable
workflow settings and startup alignment preferences; alignment is no longer only
per-window. See [workspace operation](workspace-hardware.md) for the current matrix.


Status: current implementation/operation contract, 2026-11-23. Connected unified-GUI
acceptance is pending. The previous standalone hardware result is not relabelled.

## What is enabled

| Launch mode | Spectrum / Alignment | Map / Annealing / Laser | Camera |
|---|---|---|---|
| No mode flag | Native drafts; execution disabled; no alignment tab | Native drafts; disabled | Existing independent source selector |
| `--simulate` | Synthetic, one shared spectrum worker | Existing synthetic workflows | Simulation only |
| `--hardware-spectrum` | Real HORIBA on explicit operator action | Native execution remains disabled | Existing independent source selector |

No mode probes the spectrometer during composition/window opening. The real route
imports the native wrapper only when an operation constructs its device on the
owning worker. No simulation fallback is allowed. Do not run the standalone GUI
or another application against the same HORIBA at the same time. Presets can move
the physical grating/exit mirror; use the reviewed optical configuration.

## Development-PC simulation

From `C:\Dev\labtools`, with the existing locked environment:

```powershell
$env:PYTHONPATH = (Resolve-Path ".\src").Path
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
uv run --no-sync python -m labtools workspace launch examples/workspace/working-lab/candidate.json --simulate --simulation-realtime
```

Open Alignment, choose centre/exposure and Start. Settings freeze for that run.
Stop, restart, try Spectrum while alignment is running, use Stop all, and close
while active. The new tab uses the existing light/teal cards, fixed-width scrolling
controls, plot toolbar, autoscale and frame metrics. Wheel edits remain blocked.
Alignment defaults are derived from the source-backed spectrum draft; alignment
edits are currently per-window and are not added to the flat instrument profile.

## Lab-PC real HORIBA

Commit and push the validated feature branch on the development PC. On the lab PC,
close existing LabTools/hardware-owning applications and use a clean checkout:

```powershell
if ((git status --porcelain)) { throw "Inspect local edits before switching branches" }
git fetch origin --prune
if ($LASTEXITCODE -ne 0) { throw "Fetch failed" }
git switch feature/unified-gui-alignment
if ($LASTEXITCODE -ne 0) { throw "Branch switch failed; do not reset local work" }
git pull --ff-only origin feature/unified-gui-alignment
if ($LASTEXITCODE -ne 0) { throw "Branch cannot fast-forward; stop and inspect" }
git log -1 --oneline
```

With the existing working lab environment, no dependency change is required by this
patch. If the checkout has no environment, restore the committed lock with
`uv sync --frozen --group dev`; do not improvise SDK upgrades during acceptance.
Then:

```powershell
$env:PYTHONPATH = (Resolve-Path ".\src").Path
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
uv run --no-sync python -m labtools workspace launch examples/workspace/working-lab/candidate.json --hardware-spectrum
```

The header must say Real HORIBA. Configuration identity comes from the manifest,
not an environment variable or the screenshot preference file. Use the reviewed
working-lab bundle or an explicitly reviewed source-backed manifest. Do not copy
simulation output paths or preferences into the lab configuration.

The existing source/record hashes are checked. Before native construction, source
CCD index/type/serial/dimensions/ROI/grating/mirror selection must match the deployed
wrapper preset; otherwise the operation refuses. The wrapper retains its connected
CCD identity checks. Monochromator selection remains the documented first-discovered
selection, not a new serial-number selector. Source options are expectations, not
live readbacks. No versioned profile migration is included.

## Runtime and ownership contract

`OperatorSpectrumRuntime` owns one lazy `SpectrumWorker`. Range operations use an
async facade from the existing range-panel QThread; all native construction,
connect/configure/capture/disconnect still run on the shared worker's thread/loop.
No device handles cross to Qt or the reservation executor.

Alignment uses `SpectrumWorker.start_alignment` and the existing bounded latest-frame
mailbox. The Alignment panel reserves the existing workspace owner/resource group
named Spectrum. It is intentionally an alias for the same optical resources, not
a new independent reservation. Range, alignment and overlapping map/Annealing
reservations cannot interleave. The worker and lease stay owned through cleanup.
Busy operations are refused rather than queued. Undisplayed frames may be replaced;
this is not lossless recording.

Stop all requests cooperative cancellation. Native SDK calls are not interrupted.
Closing the unified window requests Stop, keeps the window alive through cleanup,
then closes the application-owned worker automatically. A pending close suppresses
late alignment failure dialogs. A failed real operation faults the shared worker;
range and alignment cannot silently reconnect. Close the application and preserve
the traceback. Clean Stop allows restart without closing the worker.

The accepted standalone module and one-frame scripted APIs remain unchanged.
Syncerity minimum 0.065 s and Symphony minimum 0.1 s remain unchanged. Fresh dark
subtraction still captures dark then signal for each alignment frame. Camera dark
capture is independent and never moves a shutter/laser. The new route does not
energize a laser or open an Annealing shutter.

## Connected unified-GUI acceptance

Record the actual source commit, configuration ID, detector, exposure, computer,
observations and any traceback. Mark unperformed checks Not tested, not PASS.

1. Open real mode and confirm no spectrometer connection until Start/Acquire.
2. Start Alignment, observe several frames without a complete reconnect per frame.
3. Try Spectrum Test connection/Acquire while alignment runs: it must refuse busy
   without a second native connection. Try alignment during an active range job.
4. Stop alignment; wait for disconnect, then Start again without restarting Python.
5. Use Stop all during alignment; verify ownership remains busy until cleanup.
6. Stop alignment, acquire a range spectrum, then return to alignment and restart.
7. Test fresh-dark alignment on/off with the reviewed optical setup. This was not
   covered by the earlier standalone hardware record.
8. Close the unified window while alignment is active. It must remain until cleanup
   then close automatically. Reopen and verify the device is available.
9. Confirm native map, Annealing and laser controls remain disabled in this route.
   Camera is tested separately using its explicit source selector.

Do not deliberately disconnect powered hardware merely to reproduce a fault test.
Fake-transport tests cover cleanup failure; retain any naturally occurring hardware
failure evidence. This checklist is not full release approval.
