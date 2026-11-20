# Changelog

All notable changes to LabTools are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/) while the public release boundary remains
under active development.

## [Unreleased]

### Planned

- Connected-hardware acceptance against the release matrix.
- Fresh Windows wheel installation and lab-PC rollback rehearsal.
- Licence and third-party notice decisions.
- Optional dependency separation for notebooks, GUI and instrument SDKs.

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
