# Documentation status and authority

## Current all-hardware references, 2026-11-23

- [Workspace hub and all-hardware operation](workspace-hardware.md): current launch,
  settings semantics, profile requirements and connected acceptance.
- [Implementation evidence](workspace-hardware-implementation-20261123.md): actual
  tests, baseline, limits and next bounded continuation.
- Older HORIBA-only gate statements remain accurate for `--hardware-spectrum`, not
  for the new explicit `--hardware` mode. Historical acceptance records are unchanged.


## Unified alignment references, 2026-11-23

- [Unified alignment operation](unified-alignment.md): current launch modes, scope,
  ownership contract and connected acceptance procedure.
- [Implementation evidence](unified-alignment-implementation-20261123.md): actual
  tests, environment limitations, change scope and next bounded continuation.
- The 2026-11-23 sections in current-state/release-plan supersede older statements
  that unified alignment is not yet embedded. Historical audit and hardware records
  remain unchanged; no standalone result is relabelled as unified acceptance.


## Authority clarification, 2026-11-22

Status: current documentation policy. The release plan owns release gates; current
state owns the capability/evidence summary; candidate notes describe a particular
candidate. Architecture, commands and deployment references own their technical
subjects, not release approval. A newer date alone does not grant authority.

`ai-handover.md`, `release-readiness.md`, `refactor-roadmap.md` and old "next task"
paragraphs are historical where they conflict with the current release plan.
`architecture.md` contains historical checkpoints as well as implementation notes;
its dated task scheduling is not the active backlog.

- [2026-11-22 source audit](source-audit-2026-11-22.md): evidence-only findings and
  explicit dispositions, not release approval.
- [Documentation inventory](documentation-inventory-2026-11-22.md): static coverage
  and classification of every supplied project Markdown document.
- [Persistent alignment](horiba-alignment.md): current operational/API contract.
- [Unified instrument-profile proposal](next-recommendations.md#unified-working-lab-instrument-profile):
  planned work retained as an explicit exception to that file's historical preamble.
- Lab-PC acceptance files: append-only evidence on their named commits. A PASS for
  one operation does not complete a whole subsystem's release matrix.


## Purpose

LabTools contains extensive design, audit, checkpoint and migration records. Those
records are useful evidence, but they must not compete with the small set of documents
that define the current project state and release route.

## Authoritative current documents

Use these documents for current decisions:

- [Current state](current-state.md): current capability boundary, validated baseline,
  known gaps and immediate milestone.
- [Release plan](release-plan.md): release gates, acceptance matrix, deployment and
  approval criteria.
- [Repository hygiene](repository-hygiene.md): tracked-file and generated-artifact
  policy.
- [Architecture](architecture.md): current implementation boundaries and design
  decisions.
- [Development conventions](development-conventions.md): engineering and validation
  conventions.
- [Commands](commands.md): supported user and developer commands.
- [Lab-PC deployment](lab-pc-deployment.md): deployment and rollback runbook.

If statements conflict, the more specific current document above takes precedence.
Release acceptance is always governed by `release-plan.md`.

## Operational references

These remain active when their workflow is in scope:

- [Operator workspace](operator-workspace.md)
- [Intensity-map simulation](intensity-map-simulation.md)
- [Spectroscopy hardware reference](hardware/spectroscopy.md)
- [Scripted measurements](scripted-measurements.md)
- individual hardware references under `docs/hardware/`

Operational references describe procedures and behaviour. They do not independently
approve a workflow for release.

## Evidence records

Files whose names include terms such as `audit`, `checkpoint`, `repair-plan`,
`readiness`, or `gate-status` are retained as dated engineering evidence unless listed
as authoritative above. Evidence records may describe an earlier source state and must
not be treated as an active backlog without confirmation against `current-state.md` and
`release-plan.md`.

Examples include:

- comparative and device-wrapper audits
- lifecycle and transport-boundary checkpoints
- repair plans
- migration manifests
- historical readiness assessments
- previous implementation handovers

## Historical and future-design records

Documents explicitly labelled historical, superseded, proposed, target, or future are
non-authoritative. Preserve useful rationale, but move actionable work into the current
release plan before implementation.

## Maintenance rule

When adding or materially changing a document:

1. identify the document as current, operational, evidence, historical, or proposed;
2. link current decisions from this status page or the documentation index;
3. include the relevant commit, date, or candidate version in evidence records;
4. avoid duplicating procedures already maintained in an authoritative document;
5. update `current-state.md` when the capability boundary changes;
6. update `release-plan.md` when a release gate or acceptance requirement changes.

Do not bulk-delete historical records solely to reduce file count. Archive or remove a
record only after confirming that no release evidence, migration recovery, or hardware
acceptance decision depends on it.
