# Documentation index

## Operating the software

- [Commands](commands.md): current commands, aliases and real/synthetic distinction.
- [Operator workspace](operator-workspace.md): recipes, profiles and deployment caveats.
- [Intensity-map simulation](intensity-map-simulation.md): synthetic data, stop/resume and limitations.
- [Spectroscopy reference](hardware/spectroscopy.md): detector presets, dark subtraction,
  shutter wiring, diagnostic scripts, USB behaviour and laser guidance.

## Maintaining the software

Start with [AI handover](ai-handover.md). The canonical documents are
[architecture](architecture.md), [development conventions](development-conventions.md)
and [refactor roadmap / wrapper matrix](refactor-roadmap.md). Historical batch notes
below retain technical context, not competing current task lists.


- [Architecture](architecture.md): current implementation, target design and architectural decisions.
- [Development](development.md): offline checks and explicit hardware opt-in.
- [Refactor notes](refactor-notes.md): changes, compatibility and remaining work.
- [Future refactoring](future-refactoring.md): historical backlog; use the canonical roadmap for current order.

The README is the quick start. Detailed instrument procedures belong in the
hardware reference; simulation behaviour belongs in the simulation guide.
Avoid duplicating the same procedure in multiple places.


- [Spectrum processing refactor](spectrum-refactor.md): processing boundaries, compatibility and offline tests.

- [Comparative audit](comparative-audit.md): baseline/current findings, corrections and validation limits.

- [Alignment lifecycle acceptance](alignment-lifecycle-acceptance.md): blocked-job
  tests, stop/fault/deferred-close contracts, installation and Windows acceptance.

- [Lab-PC deployment](lab-pc-deployment.md): installation, protected operator access,
  offline release bundles, updates and rollback (proposed maintainer runbook).
- [Current Qt gate status](qt-gate-status.md): executed checks, skips and why map
  directory collision changes have not advanced.
