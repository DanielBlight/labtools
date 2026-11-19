# Whole-workspace simulated instrument output

## Accepted starting point

labtools_overlay_evidence_20261119T142834960654Z.txt records clean HEAD
`e9b0bcc6cb63c48648b8dbce4785f6173d177f43`, the exact eight-path camera-overlay
commit. Local validation: Ruff fixed one formatting issue then passed; 125 tests
passed with no skips; headless launch and whitespace passed; no source changes
since validation. The user confirms the camera/overlays looked good. This is not
connected-device acceptance or a measured camera-performance result.

This batch restores the other instruments' synthetic output in the current unified
operator window. It is an explicit whole-workspace launch mode, not native activation,
a per-device fallback or a second registry. The old standalone simulation launchers
remain available and unchanged. No hardware operations were performed in development.

## Launch

From the development repository:

```powershell
uv run --no-sync labtools workspace launch examples/workspace/working-lab/candidate.json --simulate
```

The same source-backed window opens with mapping, spectra, annealing and the independent
camera popup. The title/banner/status identify SIMULATION ONLY. Real camera selection
is removed in this mode; the existing camera overlay/dark controls use synthetic frames.
Nothing connects automatically. Native map/spectrum/anneal execution remains gated.

Omit --simulate to open the unchanged native candidate. Mode is selected only at
launch, not switched while workers own resources. There is no real-hardware fallback.

Optional flags:

```powershell
uv run --no-sync labtools workspace launch examples/workspace/working-lab/candidate.json --simulate --simulation-realtime
uv run --no-sync labtools workspace launch examples/workspace/working-lab/candidate.json --simulate --simulation-output 'C:\Labtools-Synthetic'
uv run --no-sync labtools workspace launch examples/workspace/working-lab/candidate.json --simulate --headless
```

Without --simulation-realtime, map and anneal waits are skipped for fast development.
With it, synthetic map integration/settle and anneal dwell/settle are honoured so Stop
and close-during-run can be exercised. This is not a timing model of SDK/device overhead.
The existing toy spectrum backend remains immediate/deterministic in either mode.
Simulation-only options without --simulate are rejected rather than ignored.

## What is simulated

- **Intensity mapping:** existing toy mirror/gate/counter backend through the existing
  InjectedSimulationServices, MapController and MapWorker. Start/stop, live map,
  resumable output and existing save/load behaviour are retained. Counter rates are
  synthetic; source addresses/pins remain provenance fields and are never contacted.
- **Spectrum:** existing toy range spectrum through SpectrumService and the existing
  async worker. Connection test, acquire, capture/reuse dark and save/plot workflows
  use synthetic data. The 64-point deterministic spectrum is not an SDK, detector
  electronics, physical gain/speed, stitching, wavelength calibration or noise model.
  Source detector-option tokens exercise the GUI but are labelled synthetic options.
- **Annealing:** new native-free synthetic grid/progress/state/log routine, injected
  into the existing AnnealWorker. It reports synthetic shutter open/closed, mirror
  position, stage coordinate and point progress, then closes the synthetic shutter,
  homes the synthetic mirror and honours the configured return-stage policy. It is
  NOT a thermal, dose, heating, shutter timing or stage motion model. Manual physical
  shutter/stage and laser controls remain unavailable; no hardware acknowledgement
  is needed to run the synthetic grid.
- **Camera:** existing synthetic source and overlays, in its independent popup. It
  can run alongside the other tabs. The camera scene is independent of the toy map/
  spectrum/anneal state; no common optical-scene coupling is claimed.

One existing WorkspaceOwnership/InstrumentSession authority still excludes conflicting
map/spectrum/anneal workflows. Reservations last through their original worker/async
cleanup. Stop all and close-during-operation include the synthetic camera and anneal.
There are no persistent native handles, hardware discovery, SDK probes or native imports.

## Settings, output and provenance

Simulation preferences use a separate per-manifest file in the existing per-user
native-workspace preferences directory, with a simulation-specific namespace. Native
preferences and standalone settings are not overwritten. The source manifest/profile/
recipes are read-only and retain their hashes and historical validation linkage.
The source map software envelope remains -10/+10 V, and explicit narrower local
anneal limits remain effective. Source defaults are expectations, not device readbacks.

Initial synthetic output defaults to `~/Labtools Simulation/Maps`, `Spectra` and
`Annealing`. Saved simulation output paths are restored independently. Explicit
--simulation-output overrides them for that launch. Corrupt/stale preference fallback
uses synthetic output roots, not the source's native output directory. Users may
still choose an output folder deliberately in the GUI. Simulation settings never
change the native backend or enable a physical operation.

Existing map metadata and spectrum/dark archives retain backend=simulation. Anneal
creates a uniquely named SIMULATED-anneal-* folder containing metadata.json,
positions.csv and result.json, all explicitly synthetic. Raw camera darks/overlays
are unchanged. A simulation dark is not a compatible native dark. No fabricated
physical serial, SDK readback or connected acceptance result is written.

## Scope and validation

Nine paths: CLI and unified window composition; new simulated session, synthetic
anneal routine and simulated panel bindings; two new tests; updated launch test; this guide. Existing native
runtime gates, acquisition algorithms, map/spectrum simulators, camera modules,
source/local configuration and old simulation launchers are unchanged. The simulated
session subclasses read-only native composition solely to reuse source validation,
limits and its single reservation authority; it overrides acquisition entry points
with fixed synthetic services, never native factories. The dormant native service
object remains gated, even when reached directly.

The guarded updater requires exact clean starting HEAD/branch and preimage hashes.
It applies only these nine paths, refuses drift and rolls back writes on failure.
--validate runs ruff check --fix, one focused simulation/native/camera regression,
headless launches in BOTH modes and whitespace. It writes a Downloads evidence file
with actual command results/JUnit/Git/source hashes. --snapshot refreshes committed
source/Git evidence without rerunning tests. Failures/skips/source changes are not
acceptance. Review source text for sensitive content before uploading.

Local acceptance: run a small synthetic map and inspect it, acquire/save a spectrum,
capture/reuse its dark, run/stop an anneal, keep the synthetic camera visible, then
exercise Stop all, close/reopen and separate settings persistence. Actual Qt tests
must pass locally. Simulation is not a replacement for native activation or lab-PC
connected-device acceptance. No packaging, ID900, new registry or physical operation
is part of this batch.

The previous launch test rejected --simulate as an unknown flag. This authorized
synthetic mode now has an explicit test asserting synthetic execution is available
while native execution/hardware remain disabled; --execute, --enable and --discover
remain rejected. This is not a weakening of the native acquisition gate.

## Actual development results

Final Ruff check --fix passed on all eight changed Python paths. Both native and
--simulate headless launches passed without hardware/environment probes. Native
execution remained false in both reports; synthetic execution was true only in
explicit simulation. Native runtime gates, native anneal acquisition/default
contracts, existing map/spectrum services and camera tools are unchanged.

The broad focused selection returned 162 passed, 5 failed, 4 skipped in 310.70s.
Two failures were test-contract corrections: the new saved-map assertion expected
nested config metadata instead of the existing flat metadata; the old launch test
still rejected --simulate. The corrected saved-map test and new explicit-simulation/
native-gate test then passed together: 2 passed in 30.10s. These results are not summed
into an invented clean full-run total. Three remaining failures are existing GUI
subprocess tests failing to import Qt on missing libGL.so.1. Four actual GUI tests
skip for that same missing runtime, including the new all-workflow/camera test.
No UI acceptance or connected-device performance is claimed here. Local --validate
runs the full focused selection unchanged, including those actual GUI checks.

The updater fixture passed dirty-tree refusal, payload-failure rollback to a clean
starting tree, exact nine staged paths/whitespace, launch/panel wiring and snapshot-
only evidence with changed-source detection. Fixture metadata is not real validation.
No hardware was operated and no local source/instrument profile was modified.
