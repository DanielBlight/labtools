# Workspace hub and all-hardware operation

Status: implemented testing route, 2026-11-23. Connected all-hardware acceptance is
pending; this document is not a hardware pass or release approval.

## Launch modes

| Mode flag | Behaviour |
|---|---|
| None | Existing native drafts; experiment execution disabled |
| `--simulate` | Synthetic map, spectrum, alignment, Annealing, laser and camera |
| `--hardware-spectrum` | Real HORIBA Spectrum/Alignment; other native experiment controls gated |
| `--hardware` | Real implemented map, Spectrum/Alignment, Annealing, ITC4000 laser and explicit camera selector |

Flags are mutually exclusive. Opening any mode does not turn on laser output, open
an Annealing shutter, move a stage or start acquisition. No simulation fallback is
used for a failed real connection. Camera still requires its explicit real source
selection and Start. The IDQ source endpoint remains 169.254.99.159:5555 in the
working-lab source bundle. No source hardware values or profile schemas are changed.

## Workspace tab

### Configuration and operating mode

Shows the configuration identity, source manifest, selected mode and local Annealing
profile. Load configuration selects another source-backed candidate manifest. It
validates/builds a replacement window in the SAME mode before closing the old one.
The old window is preserved if validation fails. Configuration switching is refused
while a workflow, camera, diagnostic or laser command is active, while any resource
is reserved, or while the real laser is connected. It is not a mode switch or a
hardware-profile editor. Unsaved settings are handled by the existing close/save
path. No source/profile file is rewritten.

### Workflow settings

Edit parameters in the workflow tabs. Workspace provides:

- Validate settings: validate current drafts without connecting devices.
- Save settings as: portable JSON of supported map/spectrum/Annealing/alignment and
  display/output preferences, bound to configuration ID, source fingerprint and mode.
- Load settings: validate the whole file before applying; restore previous controls
  if application fails. Busy loads are refused. Wrong identity/source/backend and
  hardware/limit fields are rejected, not silently adopted.
- Save as startup settings: existing atomic per-user preferences, now including
  alignment centre, exposure, preset, gain, speed and fresh-dark selection.

Settings files do not contain device handles, approval flags, hardware limits,
laser output state, reusable dark arrays or a new instrument-profile schema. Range
settings retain the existing supported preference fields; transient dark arrays
and device connection state are not exported. A simulation settings file cannot
be loaded into real mode. Output paths remain explicit and should be reviewed when
moving settings between PCs. A source change invalidates stale preferences.

### Device and workflow status

Refresh status is read-only and does not probe hardware. The table distinguishes
unopened, operation in progress, last operation released, and error/unknown states.
Most devices connect per operation; a successful previous test is not a live readback
or proof that a cable is still connected. Laser status is read after its commands;
camera status comes from the existing preview worker.

Shortcuts: Test spectrum connection, Test map connections, Connect laser controller,
and Open camera. SC10/stage diagnostics remain on Annealing. Map connection test
constructs the existing LabJack/mirror/IDQ adapters and closes the SPAD gate; it does
not scan or validate count input. Shutter test reads state; stage test reads position.
Move to anneal coordinate is an explicit movement that can change delivered power.

## Real hardware composition and limits

- Map: existing operation-scoped LabJack U6, LJTick-DAC mirror, SPAD gate and IDQ
  transport, behind the existing workspace lease. Active-high gate wiring, default
  IDQ port and U6 selection must match the deployed adapters. No new device discovery.
- Spectrum/Alignment: existing application-owned SpectrumWorker and persistent
  alignment stream, bounded mailbox, detector minima and per-frame dark ordering.
- Annealing: existing SC10/stage/mirror acquisition algorithm and cleanup ordering.
  The existing valid reviewed local flat instrument profile is REQUIRED. Source/local
  mirror and open-time limits are intersected. No source-default fallback for a
  missing/invalid profile. Explicit `--anneal-profile` is carried through validation
  and acquisition without changing process environment variables.
- Laser: one lazy worker-owned ITC4000 connection. All VISA calls remain on that
  worker. Connect performs identity/output/current readback only. Output ON and Apply
  current are separate explicit actions, refused during overlapping optical jobs.
  The established working-lab maximum and shutdown threshold are both 0.040 A; the
  real panel does NOT inherit the simulation's 0.080 A default or 0.100 A ceiling.
  This patch does not widen that policy. TEC controls are not added; the existing
  wrapper's diode/output/close semantics remain in force.
- Camera: existing UC480 path and explicit simulation/real selector; preview and dark
  capture do not control laser or shutter. No new camera driver implementation.

One workspace reservation authority is retained. The laser controller has its own
connection lease; Apply/ON temporarily reserve the shared Spectrum optical resources
so they cannot change illumination during map/Annealing/spectrum acquisition. A
stable already-selected laser output may be used during a workflow. OFF/disconnect
remain available during faults or acquisition. Stop all requests workflow cancellation
and laser diode OFF; it is not an emergency stop or an interrupt of an in-flight SDK
call. Closing waits for workers/diagnostics and laser disconnect. A failed laser
close keeps its handle/lease and the GUI available for retry; no false disconnected
state is shown. Map/Annealing/diagnostic operation failures fault further hardware
work until application teardown. Laser OFF/disconnect remain available.

## Development-PC apply and simulation

Use the single guarded updater against the supplied 560eeb3 baseline. It supports
--validate, --validate-only, --check, --print-paths and guarded --rollback. No dependency
or Git changes occur automatically. After validation:

```powershell
$env:PYTHONPATH = (Resolve-Path ".\src").Path
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
uv run --no-sync python -m labtools workspace launch examples/workspace/working-lab/candidate.json --simulate --simulation-realtime
```

Check Workspace layout, settings export/import, alignment startup restore, wrong-file
refusal and idle-only configuration switching before connected testing.

## Lab-PC launch

After committing/pushing the validated feature branch and updating the clean lab
checkout to that exact commit, use the existing working environment:

```powershell
$env:PYTHONPATH = (Resolve-Path ".\src").Path
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
uv run --no-sync python -m labtools workspace launch examples/workspace/working-lab/candidate.json --hardware
```

Annealing profile lookup is unchanged: LABTOOLS_INSTRUMENT_PROFILE if set, otherwise
%PROGRAMDATA%\Labtools\instrument.json. To select a different EXISTING reviewed
profile, append `--anneal-profile "<actual reviewed profile path>"`. Do not create a
new approved profile or copy the synthetic test profile merely to enable controls.
Workspace shows the selected profile/error. Missing profile disables Annealing but
does not prevent testing other devices. The manifest supplies spectrum configuration
identity; no LABTOOLS_SPECTRUM_CONFIGURATION_ID variable is needed.

Close competing hardware-owning applications. Presets can move grating/exit mirror;
stage moves and Annealing can change delivered power/open the shutter. Use the
reviewed optical setup and existing physical interlocks. No typed safety phrase or
new approval ritual is introduced. Device selection limitations (first-discovered
monochromator/U6/stage/camera where already used) remain; this is not a new selector.

## Connected testing order

Record the actual commit/configuration/profile and observations; mark untested items
Not tested. Do not copy previous standalone passes into unified acceptance.

1. Open --hardware: confirm Real hardware badge, expected configuration/profile and
   no automatic connection, motion, shutter opening or laser activation.
2. Test spectrum connection; run alignment several frames, Stop/restart, Stop all,
   range/alignment handoff and active close. Test fresh-dark on/off separately.
3. Test map connections, then a small reviewed map. Confirm mirror/count operation,
   gate cleanup, Stop and exclusion with spectrum/Annealing.
4. Test SC10 state and stage position. Only then explicitly move to the reviewed
   coordinate and run the existing minimal Annealing rehearsal with the reviewed
   optical setup. Confirm Stop/close cleanup, shutter close and return stage/home.
5. Connect ITC4000 and check identity/output/current readbacks. Connection does not
   change output. Test Output ON only as a separate intentional powered check at
   the preserved limit, then Output OFF, Stop all and disconnect/close.
6. Select the real camera source explicitly and test preview/Stop/dark independently.
7. Check settings save/reload and configuration-switch refusal while active/connected.

Do not deliberately unplug powered devices to reproduce fake fault tests. Preserve
any naturally occurring error and the actual cleanup state. Linux fake-device tests
and source enablement do not establish connected acceptance or release approval.
