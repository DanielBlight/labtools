# LabTools current state

## Status

LabTools is in late development and release-candidate preparation for a controlled
internal laboratory pilot. The current intended candidate is `0.2.0-rc.1`; the
installed project version remains `0.1.0` until release engineering is complete.

The latest validated offline baseline is:

- Python 3.12 on Windows
- 1,206 non-hardware tests passed
- unified operator workspace implemented
- simulated intensity mapping and spectroscopy implemented
- independent camera preview with overlays, annotations and dark correction implemented
- Annealing workflow integrated but separately gated for physical acceptance
- repository export tooling split into quick-development and full-project bundles

Passing offline tests does not constitute connected-hardware approval.

## Authoritative documents

- [Release plan](release-plan.md): forward-looking release gates and acceptance route.
- [Repository hygiene](repository-hygiene.md): tracked-file and generated-artefact policy.
- [Architecture](architecture.md): implementation boundaries and design decisions.
- [Development conventions](development-conventions.md): engineering and validation rules.
- [Commands](commands.md): supported launch and command-line entry points.
- [Lab-PC deployment](lab-pc-deployment.md): deployment and rollback runbook.

Other audits, checkpoints and repair plans are evidence records unless one of the
current documents links to them as an active requirement.

## Implemented capability boundary

### Offline and simulated

- intensity-map acquisition, cancellation, persistence and simulation
- spectrum acquisition and simulation
- hyperspectral scripted simulation
- camera preview, synthetic preview, annotations, crosshair and concentric overlays
- dark-frame capture, persistence and subtraction
- versioned measurement recipes and dispatch
- unified operator workspace and workflow ownership
- configuration validation and fake-transport contract coverage

### Real-device integrations present in source

The source tree contains integrations for HORIBA spectroscopy, UC480 camera operation,
Keithley measurement, LabJack/mirror control, SC10 shutter control, Kinesis rotation,
ITC4000 control and IDQ timing. Presence in source is not equivalent to release
acceptance. Each supported device must complete the hardware matrix in the release plan.

### Separately gated

Laser Annealing remains independently gated because physical acceptance must cover
shutter closure, laser-current control, mirror homing, stage ownership, partial-start
cleanup, cancellation, emergency procedure and recovery. The configured maximum
shutter-open time is 43,200 seconds (12 hours).

## Known release gaps

- Windows CI is defined; the first authoritative hosted run remains to be recorded
- no formal wheel-based release candidate has been fresh-installed and rehearsed
- connected tests are not yet comprehensively classified with hardware/subsystem markers
- licence and third-party notice decisions remain outstanding
- optional analysis, notebook and Napari dependencies are separated; instrument extras remain future work
- physical instrument acceptance and lab-PC rollback evidence remain incomplete
- historical documentation still needs gradual classification or archival

## Immediate next milestone

Complete release engineering before further broad GUI work:

1. record the first successful hosted Windows CI run
2. add versioned changelog and candidate release notes
3. establish licence and third-party notices
4. build and install `0.2.0-rc.1` in a fresh environment
5. complete the connected-hardware acceptance matrix
6. rehearse side-by-side lab-PC installation and rollback

## Validation rule

A clean non-hardware run is necessary but not sufficient for release. A workflow is
supported only when its offline evidence, connected-device evidence, deployment route
and rollback procedure are all recorded against the same candidate commit.
