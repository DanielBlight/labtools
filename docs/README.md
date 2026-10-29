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

- [Device-wrapper audit](device-wrapper-audit.md): per-module evidence, consumer inventory,
  rewrite decisions and code-level risks (no runtime repair).
- [Wrapper repair plan](device-wrapper-repair-plan.md): bounded tasks, compatibility and
  fake/physical acceptance requirements.
- [Current wrapper-audit checkpoint](wrapper-audit-checkpoint.md): gate results,
  installation/rollback/commit commands and continuation.

- [ITC4000 lifecycle W1 checkpoint](itc4000-lifecycle-checkpoint.md): implementation,
  fake-transport evidence, exact inventory, install/rollback/commit and next task.

- [HORIBA lifecycle W2 checkpoint](horiba-lifecycle-checkpoint.md): implementation,
  fake-SDK/backend/worker evidence, exact inventory, installer and next task.

- [Scanning-mirror W5 checkpoint](scanning-mirror-preflight-checkpoint.md): DAC preflight, partial-movement reporting, tests and installer.

- [UC480 lifecycle checkpoint](uc480-lifecycle-checkpoint.md): partial-start rollback, cleanup evidence and installer.

- [SC10 lifecycle checkpoint](sc10-lifecycle-checkpoint.md): serial ownership, transcript tests and installer.

- [Scriptable measurements](scripted-measurements.md): target public automation API and usage.
- [Kinesis lifecycle checkpoint](kinesis-lifecycle-checkpoint.md): validation and close ownership.
