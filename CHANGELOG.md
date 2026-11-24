# Changelog

All notable changes to LabTools are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) while the public release boundary remains
under active development.

## [Unreleased]

### Added (mirror positioning, 2026-11-23)

- Source-bound Mirrors popup next to Camera with explicit X/Y/Home commands,
  shared optical exclusion and Stop/close cleanup; no move on open/close.
- Spectrum sequence X/Y/settle settings applied before baseline and each later
  spectrum on the existing spectrum worker, with configured home afterward.
- Position metadata in sequence journals/retained exports and Workspace settings.

### Added (retained output, 2026-11-23)

- Optional hyperspectral output and unified Save results actions for retained
  spectrum/map/cube/Annealing runs and complete baseline-first sequences.
- Unique numeric NPZ/JSON data-provenance exports without hardware reacquisition.
- No-run-file intensity maps when unified saving is off; existing standalone
  checkpoint semantics and automatic output formats remain unchanged.

### Changed (retained output, 2026-11-23)

- Full-area sequence spectrum/intensity plots and two-panel hyperspectral results.
- Compact Annealing Instruments section with Output below it outside the scroll area.
- Concise sequence summary rather than raw result dictionaries.

### Changed (workflow UX, 2026-11-23)

- Combined dose modes with shared Annealing controls under one visible tab.
- Independent hyperspectral spatial grid and live latest-only pixel/spectrum display.
- Alignment moved to a reopenable modeless popup from Spectrum, retaining shared ownership.
- Sequences now take one pre-anneal baseline measurement then one anneal/measurement
  pair per cycle, with optional disk output and latest/live measurement results.
- Full-width output rows and source-bound persistence for new controls; legacy phase
  counts accepted but ignored. Existing hardware limits and profile schema unchanged.

### Added (experiment workflows, 2026-11-23)

- Single-point and per-point linear/logarithmic dwell-array programs with dose preview,
  existing per-point shutter/stage cleanup, source/local validation and saved plans.
- Unified hyperspectral tab using the shared native spectrum worker, exclusive mirror/
  spectrum ownership, partial cube archives and selectable pixel spectra.
- Exclusive anneal-then-measure sequences with independent phase/cycle repeat counts,
  all three measurement choices, cooperative Stop/close and per-step output journals.
- Workspace settings persistence for the new controls and qualified baseline lab-PC
  acceptance recording, including the supplied 630-pass Windows validation.

### Fixed (experiment workflows, 2026-11-23)

- Camera form-field clipping and narrow-window intensity-map Y-axis margin handling.

### Added (workspace hardware, 2026-11-23)

- Workspace configuration/status hub with source/mode/profile summary, device status,
  explicit test shortcuts, source-bound settings import/export, alignment startup
  preferences and idle-only configuration switching.
- Explicit all-hardware mode for existing real map, Spectrum/Alignment, Annealing,
  laser and camera paths; opening/connecting never implicitly enables laser output.
- Asynchronous single-owner ITC4000 controls preserving the 0.040 A working-lab limit,
  laser OFF on Stop all and disconnect-aware deferred close with retryable failures.
- Worker-bound SC10/stage diagnostics and profile-validated Annealing, retaining the
  existing acquisition/cleanup algorithm and strict flat instrument profile.
- Focused runtime and actual Qt tests plus operation/acceptance documentation.

### Added (unified alignment, 2026-11-23)

- Unified Alignment tab matching the existing operator controls/plot layout.
- One application-owned spectrum worker shared by range and continuous alignment,
  retaining workspace ownership through capture, cancellation and disconnect.
- Explicit `--hardware-spectrum` launch for real HORIBA Spectrum/Alignment only;
  the default native candidate and other native workflow gates remain disabled.
- Alignment-aware Stop all and automatic parent-window close after worker cleanup.
- Runtime and actual offscreen Qt regression coverage, source identity checks and
  documented Windows/connected-device acceptance steps. No hardware pass is inferred.

### Fixed (alignment GUI follow-up, 2026-11-23)

- Pace simulated continuous alignment without changing real acquisition timing or
  one-shot APIs; check Stop during short pacing waits.
- Always stop and close the injected worker when the repeat/stop/close GUI test
  fails, avoiding a live stream during pytest traceback reporting.
- Add four Qt-free pacing regressions. Windows GUI acceptance remains pending;
  see `docs/source-audit-2026-11-23-alignment-followup.md`.


### Fixed

- Continuous HORIBA alignment now holds one worker-owned backend session per
  Start/Stop run instead of opening a connection for every displayed spectrum.
- Alignment and range adapters share the existing process-local HORIBA ownership
  guard, including separate worker/service instances using these adapters.

### Changed

- Added a Qt-free latest-frame mailbox and continuous worker API for later unified
  GUI integration; retained the scripted single-frame API and detector minima.
- Reconciled current-state, release-gate and documentation-authority descriptions;
  retained historical hardware records without promoting them to full acceptance.

### Validation

- See `docs/source-audit-2026-11-22.md` for the exact non-Qt test scope, lint baseline
  comparison and missing Windows Qt/hardware evidence. No new release is declared.

### Planned

- Connected-hardware acceptance against the release matrix.
- Fresh Windows wheel installation and lab-PC rollback rehearsal.
- Licence and third-party notice decisions.
- Remaining optional dependency separation for GUI and instrument SDKs; analysis,
  notebooks and Napari extras are already present.

## [0.2.0-rc.1] - 2026-11-20

### Added

- Unified operator workspace for mapping, spectroscopy, Annealing and laser control.
- Independent camera preview with explicit simulation, annotations, crosshair,
  concentric overlays and dark correction.
- Quick-development and complete-project text export tools.
- Authoritative release plan, current-state record and repository-hygiene policy.
- Windows CI definition for Ruff, non-hardware tests and distribution builds.

### Changed

- Rebuilt and standardised the compact operator GUI.
- Improved map responsiveness and explicit cancellation behaviour.
- Refined camera and Annealing layouts.
- Set the Annealing maximum shutter-open configuration to 12 hours.
- Removed the legacy root spectrum launcher and generated measurement artefacts.
- Standardised repository line endings and documentation authority.

### Validation

- 1,206 non-hardware tests passed on Windows with Python 3.12.6.

### Release boundary

This is a release candidate for a controlled internal pilot, not connected-hardware
approval. Real workflows remain conditional on the hardware acceptance matrix,
side-by-side lab-PC deployment and rollback rehearsal.
