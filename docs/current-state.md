# LabTools current state

## Unified alignment implementation, 2026-11-23

The unified workspace now embeds an Alignment tab beside Spectrum in explicit
simulation and real-HORIBA modes. Both panels share one application-owned
`SpectrumWorker`; the existing workspace Spectrum reservation is held through
operation and cleanup. Stop all includes alignment, and parent close waits for
cleanup before automatically closing the worker/window.

The new explicit `workspace launch ... --hardware-spectrum` route enables real
HORIBA Spectrum and Alignment only. It does not enable native map, Annealing or
laser execution. Camera source selection remains independent. The default launch
without flags remains disabled; `--simulate` stays native-free. See
[unified alignment operation](unified-alignment.md) and
[implementation evidence](unified-alignment-implementation-20261123.md).

The committed [standalone hardware record](acceptance/lab-pc/horiba-alignment-persistent-session-20261123-113622.md)
passes Start/multiple frames/Stop/restart on tested source `714405a2cdee2667db2d4a0fcf3261b93cc98627`.
It explicitly leaves dark-subtracted acquisition and active-close untested. This
record supersedes the older reconnect failure only for its observed standalone
lifecycle; it does not establish unified-GUI hardware acceptance. No new connected
hardware result is claimed by this implementation.

The dated 2026-11-22 notes below describe the preceding repair. Where those notes
say alignment is not yet embedded, this section is the current state.


## Source review update, 2026-11-22

Status: current capability register. See [source audit](source-audit-2026-11-22.md)
for evidence, limitations and the cleanup register.

Continuous alignment now has a service-level persistent session and a bounded,
Qt-free worker frame mailbox. The standalone window consumes this stream. It is
not yet integrated into the unified workspace. Existing one-frame scripted APIs
remain one-shot. Windows Qt and connected-HORIBA acceptance of this repair remain
outstanding; do not treat the earlier alignment FAIL as closed.

The [lab-PC record](acceptance/lab-pc/hardware-acceptance-20261120-181733.md)
contains initial camera and HORIBA spectrum passes, ITC4000 shutdown-limit evidence,
map orchestration, Annealing dry-run/cancellation and a minimal powered pass. These
are bounded observations on recorded earlier commits, not blanket release approval.
IDQ nonzero count-input evidence remains pending. Alignment failed its connection
lifecycle check. Packaging, rollback and candidate-wide evidence still need closure.

The [versioned instrument-profile migration](next-recommendations.md#unified-working-lab-instrument-profile)
remains planned, not implemented. Do not extend the strict flat Annealing profile
ad hoc while integrating alignment.


## Status

LabTools is in late development and release-candidate preparation for a controlled
internal laboratory pilot. The source package version is `0.2.0rc1` in `pyproject.toml`
(displayed as `0.2.0-rc.1` in release notes). The lab record also uses the label
"RC2 profile freeze"; this is not a package-version increment or a new release.
The uploaded baseline is `54ce3563385734f49be567e27530562a14c64014` on
`fix/alignment-persistent-session-v2`. This document does not establish what is
installed on any PC today.

The previously recorded Windows offline baseline is (not a fresh result for this repair):

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
2. maintain the existing changelog and candidate release notes
3. establish licence and third-party notices
4. build and install `0.2.0-rc.1` in a fresh environment
5. complete the connected-hardware acceptance matrix
6. rehearse side-by-side lab-PC installation and rollback

## Validation rule

A clean non-hardware run is necessary but not sufficient for release. A workflow is
supported only when its offline evidence, connected-device evidence, deployment route
and rollback procedure are all recorded against the same candidate commit.
