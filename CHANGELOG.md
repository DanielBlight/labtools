# Changelog

All notable changes to LabTools are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) while the public release boundary remains
under active development.

## [Unreleased]

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
