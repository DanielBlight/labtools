# LabTools release plan

## Gate status reconciliation, 2026-11-22

Status: current release-gate authority. Detailed [audit](source-audit-2026-11-22.md).
The required-work lists below are gate definitions, not claims that every item is
still absent. Completed source work must not be repeatedly reimplemented.

| Gate | Present in the supplied source | Still required or unverified |
|---|---|---|
| 0 hygiene | Export tools consolidated; legacy root launcher and cited generated outputs absent; clean status reported in manifest | Migration-retention policy conflict; final candidate clean-tree check |
| 1 engineering | Windows CI definition, `0.2.0rc1` metadata, changelog, candidate notes, validation/build scripts | Hosted CI evidence, locked full-suite pass, built artefacts, fresh functional install; licence/notices decisions |
| 2 dependencies | `analysis`, `notebooks`, `napari` extras separated | Instrument/GUI optionality remains a deliberate packaging decision |
| 3 hardware | Bounded lab-PC evidence exists for camera, spectrum, ITC4000 and Annealing | Complete per-workflow matrix on the frozen candidate; alignment retest; IDQ nonzero counts |
| 4 operator | Earlier dry-run, cancellation and minimal powered observations | Complete packaged-candidate rehearsal; do not extrapolate full fault/power-loss coverage |
| 5 deployment | Deployment and rollback runbooks/scripts exist | Actual side-by-side installation and rollback evidence |
| 6 decision | Candidate release notes exist | Explicit supported/excluded scope and approval record |

The source version remains `0.2.0rc1`. "RC2 profile freeze" in the lab record is
an evidence label, not a released `0.2.0rc2` package. The 1,206-test baseline below
is historical Windows evidence, not this repair's result. The audit found 44 Ruff
findings with the available non-locked Ruff version, identical before and after this
repair; the locked Windows gate must resolve or explain them, not assume green.

The hardware matrix below lists required evidence, not a denial that partial passes
exist. Read it alongside the [lab-PC record](acceptance/lab-pc/hardware-acceptance-20261120-181733.md).
No row is promoted to full acceptance by this documentation update.

Alignment is an explicit repair gate: one connect/configure/move per Start, repeated
frames on the same thread/loop, busy refusal until Stop/close teardown, one disconnect,
and repeat Start without reboot. The implementation is now present; Windows Qt and
connected-device acceptance remain pending. Unified-GUI integration is the next
bounded feature task after this lifecycle is accepted, not a broad controller rewrite.

The [unified profile proposal](next-recommendations.md#unified-working-lab-instrument-profile)
remains deferred until the current acceptance/freeze cycle completes. Alignment must
reuse reviewed configuration identity and existing detector limits in the meantime.


## Purpose

This document defines the bounded route from the current development branch to the first controlled internal LabTools release. It is the authoritative forward-looking release plan. Historical audits, migration records, lifecycle checkpoints, and older readiness documents remain evidence records but do not supersede this plan.

## Current baseline

- Intended first candidate: `0.2.0-rc.1`
- Release class: controlled internal laboratory pilot
- Supported platform: Windows 64-bit
- Python baseline: Python 3.12
- Offline validation baseline: 1,206 non-hardware tests passed
- Unified operator workspace implemented
- Simulation workflows implemented
- Camera and Annealing layout refinements implemented
- Connected-hardware acceptance remains a separate release gate

The codebase is at late-development quality. It is not yet an unrestricted laboratory release because connected-instrument, packaging, deployment, rollback, and operator-acceptance evidence remain incomplete.

## Release principles

1. Release a bounded and explicitly supported workflow set.
2. Do not treat simulation or fake transports as physical instrument acceptance.
3. Freeze broad feature work once the release candidate is created.
4. Preserve simulation and development modes without connecting to hardware by default.
5. Require explicit operator actions before opening real devices.
6. Record the exact commit, dependencies, machine, instruments, and evidence used for the release decision.
7. Keep installation, operator data, and rollback copies separate.
8. Gate Laser Annealing independently from lower-risk workflows.

## Proposed first release

### Candidate identity

- Version: `0.2.0-rc.1`
- Release class: internal controlled pilot
- Installation model: side-by-side candidate installation
- Candidate source: clean, tagged Git commit
- Environment: locked dependencies from `uv.lock`
- Build artefact: Python wheel plus deployment instructions
- Operators: named and briefed laboratory users only

### Provisional candidate workflows

A workflow may be included only after completing its hardware acceptance row.

- Unified operator workspace
- Offline and simulated intensity mapping
- Offline and simulated spectroscopy
- Camera preview and annotation
- Real spectroscopy, conditional on HORIBA acceptance
- Real camera preview, conditional on UC480 acceptance
- Mirror positioning, conditional on controller and coordinate acceptance

### Separately gated Laser Annealing workflow

Laser Annealing additionally requires documented acceptance of:

- shutter opening and closure
- shutter-close failure handling
- laser-current control
- mirror positioning and homing
- rotation-stage ownership
- partial-start cleanup
- cancellation and close refusal
- maximum-open-time behaviour
- emergency-stop procedure
- power-loss and relaunch procedure

The configured maximum shutter-open time is 43,200 seconds, or 12 hours. This software limit is not a substitute for physical safety controls or operator procedures.

## Gate 0: repository hygiene

### Required work

- Remove the tracked `labtools_source_*.txt` historical snapshot.
- Remove `new_labtools_snapshot copy.ps1`.
- Consolidate project-export tooling under `scripts/development/`.
- Remove or relocate `project_upload.txt`.
- Decide whether committed intensity-map output is a fixture or generated data.
- Move genuine fixtures to `tests/fixtures/`.
- Exclude runtime output directories from Git.
- Review `.labtools-migrations` and document retention or archival.
- Remove the legacy root `main.py` unless compatibility evidence requires it.
- Ensure no `.before_*`, local exports, caches, or operator outputs are tracked.
- Reach a clean working tree.

### Exit criteria

- `git status --short` produces no output.
- No duplicate snapshot/export scripts remain.
- Runtime output is outside the tracked source tree.
- Migration-history retention has a documented decision.

## Gate 1: automated release engineering

### Required work

- Add Windows continuous integration using Python 3.12.
- Recreate dependencies from the lockfile.
- Run Ruff over active source, tests, scripts, and examples.
- Run the complete non-hardware test suite.
- Build a source distribution and wheel.
- Install the wheel into a fresh environment.
- Smoke-test supported command-line entry points.
- Add `CHANGELOG.md` and candidate release notes.
- Add a University-approved `LICENSE`.
- Add `THIRD_PARTY_NOTICES.md`.
- Confirm redistribution terms for vendored IDQ and Cryostation material.
- Document the approved security-reporting route.

### Minimum automated commands

```powershell
uv sync --frozen --group dev
uv run ruff check --fix src tests scripts examples
uv run pytest -q -ra -m "not hardware"
uv build
```

### Exit criteria

- CI passes on Windows.
- Non-hardware tests pass.
- Wheel and source distribution build.
- Fresh-environment installation succeeds.
- Supported CLI launch smoke succeeds.
- Version and changelog identify the candidate.

## Gate 2: dependency and packaging boundary

Separate optional dependency groups where practical:

- `gui`
- `analysis`
- `horiba`
- `camera`
- `labjack`
- `visa`
- `napari`
- `notebooks`
- `dev`
- `all`

Jupyter, JupyterLab, IPykernel, Napari, and instrument-specific SDKs should not be mandatory for every installation unless the release candidate requires them.

### Exit criteria

- Operator installation contains only required dependencies.
- Unsupported SDKs are not installed merely because another workflow needs them.
- The release environment can be recreated on a clean Windows machine.

## Gate 3: hardware acceptance matrix

| Device or subsystem | Exact identity | Fake transport | Connected start | Normal completion | Stop/cancel | Failure cleanup | Relaunch | Data evidence | Status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| HORIBA spectrometer | Record model and SDK | Required | Required | Required | Required | Required | Required | Required | Pending |
| UC480 camera | Record model and SDK | Required | Required | Required | Required | Required | Required | Required | Pending |
| Keithley SourceMeter | Record model and transport | Required | Required | Required | Required | Required | Required | Required | Pending |
| Mirror/LabJack control | Record model and wiring | Required | Required | Required | Required | Required | Required | Required | Pending |
| SC10 shutter | Record serial identity | Required | Required | Required | Required | Required | Required | Required | Pending |
| Kinesis rotation stage | Record serial and SDK | Required | Required | Required | Required | Required | Required | Required | Pending |
| ITC4000 | Record VISA identity | Required | Required | Required | Required | Required | Required | Required | Pending |
| IDQ controller | `169.254.99.159` | Required | Required | Required | Required | Required | Required | Required | Pending |

### Test classification

Tests must be classified as:

1. unit and contract tests
2. fake-transport integration tests
3. connected-hardware acceptance tests

Connected tests must use registered markers such as:

```python
@pytest.mark.hardware
@pytest.mark.uc480
```

The non-hardware suite must not depend on personal `QSettings`, connected SDKs, device availability, operator output directories, or previously generated data.

### Exit criteria

A workflow is supported only when every required cell in its applicable device rows is complete and linked to recorded evidence.

## Gate 4: physical operator rehearsal

For every candidate workflow:

1. Start from the packaged release candidate.
2. Confirm display and configuration loading cause no unintended connection.
3. Connect or start using the explicit operator control.
4. Run a normal acquisition.
5. Stop near the beginning.
6. Stop near the end.
7. Attempt to close while active and confirm safe refusal.
8. Exercise a defined device or communication failure.
9. Confirm worker and device ownership are released.
10. Repeat without rebooting.
11. Confirm outputs, metadata, timestamps, and configuration identity.
12. Confirm operator data is outside the installation directory.
13. Record logs, screenshots, output hashes, and observations.

### Annealing-specific rehearsal

- verify approved shutter-open sequence
- verify approved shutter-close sequence
- verify shutter-close failure handling
- verify mirror-home behaviour and failure handling
- verify stage and laser-controller cleanup
- verify Stop during each active phase
- verify the configured 12-hour maximum
- verify the external emergency procedure
- verify recovery after application or power interruption

## Gate 5: lab-PC deployment and rollback

### Required work

- Install the candidate side-by-side with the current installation.
- Record the lab-PC identity and Windows version.
- Record Python, driver, SDK, VISA, and serial dependencies.
- Verify operator permissions and writable output locations.
- Verify settings persistence.
- Verify the documented desktop or Start-menu launch route.
- Verify ordinary operation does not require the source checkout.
- Verify data remains separate from the installed package.
- Rehearse rollback to the previous known-good installation.
- Record the exact rollback path and responsible person.

### Exit criteria

- Candidate launches through the documented operator route.
- Supported devices are discoverable only by explicit action.
- Operator outputs are writable and retained.
- Rollback is demonstrated.
- Reinstallation from recorded artefacts is repeatable.

## Gate 6: release decision

The release record must include:

- release version
- Git commit and tag
- build artefact hashes
- lockfile hash
- supported and excluded workflows
- non-hardware test summary
- connected-hardware evidence
- laboratory machine and instrument identities
- known issues
- operator names or group
- installation and rollback locations
- approval date and approver

Possible decisions:

- approved for controlled pilot
- approved with explicit restrictions
- rejected pending named evidence
- withdrawn after deployment

## Known technical debt

The following are improvements but not automatic pilot blockers:

- large GUI modules
- widget reparenting in the studio layout
- duplicated historical documentation
- expected Qt offscreen warnings
- Pydantic `json_encoders` deprecation
- optional dependency consolidation
- post-pilot decomposition of `workspace_studio.py`
- direct construction of studio views rather than legacy-widget reuse

Do not perform a broad GUI or controller rewrite immediately before hardware acceptance.

## Documentation consolidation

Maintain three release-decision documents (technical subject authorities remain
listed in `document-status.md`):

- `docs/current-state.md`
- `docs/release-plan.md`
- candidate-specific release notes

Move older audits, superseded plans, and completed checkpoints under `docs/history/`, or label every document as current, superseded, planned, or evidence-only.

## Original milestone sequence

The sequence below is retained for orientation. Its estimates are historical planning
assumptions, not a new delivery commitment. Use the gate status above for remaining work.

### Milestone 1: clean candidate source

Estimated effort: 0.5 to 1 development day.

- complete repository cleanup
- decide migration-history retention
- remove duplicate exporters and generated outputs
- reach a clean working tree

### Milestone 2: reproducible release candidate

Estimated effort: 1 to 2 development days.

- add CI
- add licence and third-party notices
- add changelog
- assign `0.2.0-rc.1`
- build and fresh-install the wheel
- verify launch entry points

### Milestone 3: bounded hardware evidence

Estimated effort: 1 to 3 laboratory sessions.

- start with spectroscopy and camera
- complete mirror and SourceMeter acceptance
- gate Annealing separately
- record all evidence against the matrix

### Milestone 4: deployment rehearsal

Estimated effort: 0.5 to 1 day.

- side-by-side lab-PC installation
- operator smoke test
- data-location validation
- rollback rehearsal

### Milestone 5: controlled pilot

- freeze the candidate
- issue release notes
- approve supported workflows
- brief named operators
- collect pilot feedback without uncontrolled feature work

## Release readiness definition

LabTools is ready for the controlled pilot when:

- the repository is clean
- CI is green
- the package builds and installs from recorded artefacts
- the non-hardware suite is green
- every supported workflow has connected-hardware evidence
- unsupported workflows are clearly unavailable or labelled
- lab-PC deployment and rollback have been rehearsed
- the release record is approved

Until all conditions are met, the project remains a release candidate rather than a released laboratory control system.
