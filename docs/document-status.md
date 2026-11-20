# Documentation status and authority

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
