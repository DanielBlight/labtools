# Release readiness: R1 controlled spectroscopy pilot

## Authoritative scope correction and evidence closure (2026-11-05)

**R1 must include laser control, IDQ, mapping and annealing, in addition to spectroscopy.**
The maintainer explicitly rejected the HORIBA-only reduction. The older pilot scope,
exclusion of these required workflows and its 3-5 checkpoint estimate below are
SUPERSEDED, not approved. Required functionality is now recorded; exact device/preset,
laser/TEC limits, optical-path arrangements, operator/process policy and physical
acceptance are not approved by a feature request. No hardware execution is authorized.

Latest supplied source remains labtools_source_20261105_140459.txt, HEAD
e0ef68bd5ec8c54bf0a075565fe5b0050a2cba25, feature/shared-instrument-session,
upstream +9/-0, tracked worktree/index clean. No newer source snapshot was attached
with the logs. All five release-plan payloads match their backup. The ITC source and
tests match the implemented guard; later roadmap/handover pointers are expected docs
evolution, not code regression. Preserve all original data, artifacts and backups.

### Supplied local evidence: accept and reuse, do not repeat 195 tests

The actual attached lint.log says All checks passed. targeted.log reports 195 passed,
16 Pydantic json_encoders deprecation warnings, 16.07 seconds. targeted.xml reports
195 tests, zero failures/errors/skips, time 16.069 seconds, timestamp
2026-11-05T13:51:20.143236+00:00. XML testcase inventory is 55 readback, 96 finite-input,
44 lifecycle. These are actual local artifact outcomes, not a new assistant run.
No separate terminal process exit codes or exact lint invocation were attached;
do not invent them or extend a one-line lint pass to the entire repository.

Byte lengths and SHA-256 of all three attachments exactly match the latest snapshot
manifest entries in
.labtools-validation/itc4000-readback-implementation-20261105T1351092790054Z/:

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| lint.log | 42 | af352a86840ad0af3d37ea0d9197f868363a6dac6b1c2ef5d2722f6b41d2d9af |
| targeted.log | 2276 | 7bd30000af4594f9832226b2d36bf6fd0742fe2246e14d2508263a0f13054b68 |
| targeted.xml | 28963 | c3443825b4a3867c8dc9c53314e47ba570a9780c84d21f20f02baf40585fa618 |

This links the supplied artifacts to the snapshot inventory and current matching
ITC source/test payloads. It is not a cryptographic run-time source attestation or
proof of a clean full suite. Close the prior 'raw ITC outcomes unavailable' subitem;
retain missing command/exit provenance separately. No reason to rerun those 195
unchanged cases merely to reconfirm. Warnings are not failures and are not automatically
release blockers; classify their impact rather than opportunistically refactoring.

### Revised blocker register (supersedes narrower matrix below)

| ID | Required workflow / evidence | Current status and next criterion |
| --- | --- | --- |
| X0 scope | Spectroscopy + laser + IDQ + mapping + annealing required. | Feature scope confirmed by maintainer. Exact operating configurations, approved limits, IDQ modes and mapping type, concurrency/access arrangements and operator policy remain open; no safety/physical approval inferred. |
| X1 ITC software | Supplied local logs/XML, matching snapshot hashes; W1b and setter readback source/tests unchanged. | 195 local targeted passes accepted; lint artifact pass accepted for its original unspecified invocation. No repeat targeted run. Broader candidate lint/Qt/offline/build still missing. Getter/GUI second-read, enable/delay/timeout questions remain separate review items before laser acceptance, not automatically repaired here. |
| X2 IDQ | ID900 required. runtime/idq_count_service.py uses simultaneous counts; acquisition/intensity_map.py:524 calls get_simultaneous_counts. Histogram controller.py:412 still eval(raw). | Counters/mapping are not automatically histogram consumers. Record exact required IDQ modes before deciding applicability. Histogram parser work stays explicitly deferred, P0 open; if histograms are required, that unresolved evidence dependency blocks that capability. Do not waive it, fabricate fixtures or reopen collection automatically. DLT/timestamp modes need their own consumer/acceptance review if required. |
| X3 mapping | Existing intensity-map path and tests; timestamp allocation intensity_map.py:83-84,425-428 can fail on collision. | Mapping now in scope: collision handling is a demonstrated limitation to triage against required repeated-run behavior, not claimed overwrite. Cancellation/resume/output preservation and shared IDQ/LabJack ownership need candidate evidence and supervised acceptance. Real hyperspectral GUI is not silently promised; it remains simulation-only. |
| X4 annealing | acquisition/laser_anneal.py:140-306; config/anneal_workspace.py validation; tests/test_anneal_workspace.py; CLI optical-path confirmation. | Existing workflow needs offline evidence and reviewed SC10/mirror/LabJack/rotation-stage cleanup/cancellation and optical-path procedure. A CLI confirmation is not an interlock or physical safety certification. No laser output or shutter/motion is executed here. |
| X5 broad software/build | Existing seven-file source-audit runner cannot alone cover expanded scope; full gate can permit skips. | One remaining-offline run excluding already accepted ITC modules and hardware modules, all source/test lint, selected Qt presence/zero skips, source/lock hashes, wheel and staging smoke. Actual failures are classified by workflow/root cause, not auto-fixed. |
| X6 native/operator/physical | No new native-driver or physical evidence supplied. | Separate supervised acceptance per required workflow and shared-resource interaction, with approved device/limits/operator procedures. Offline passes do not close this. |
| X7 deployment | Existing protected-wheel/data separation/rollback proposal. | Candidate build/staging smoke can be prepared now. Active lab-PC install, permissions, driver setup, rollback rehearsal and release decision remain later gates. |

### One bounded Windows handoff, no source repairs

Use the delivered run_labtools_expanded_r1_evidence_v1.py from the repository root
with the existing .venv and uv --no-sync. It requires this HEAD and exact source/test/
lock hashes; it allows only the three supplied documentation edits. Run BEFORE
committing this docs update, then stage/commit docs. It records actual HEAD and raw
source hashes before/after, commands/exit codes/timeouts, environment, raw logs/XML,
collection/deselections, excluded hardware paths, reused ITC artifacts and wheel hash
in a unique .labtools-validation/expanded-r1-* directory. No old evidence is overwritten.

The runner checks/reuses exact original ITC artifacts and excludes their three test
modules from the remaining offline run. It excludes known hardware modules before
collection, uses -m 'not hardware', no --run-hardware, and disables external pytest
plugin autoload. Selected Qt modules must appear; any skips/errors/failures/timeouts
prevent automatic evidence-complete status. Full skip details remain for review.
This is offline test selection, not a security sandbox for arbitrary changed code;
source guards refuse changed Python. No diagnostics/discovery or native hardware test.

Lint covers src and tests to capture the expanded candidate, but any findings must
be classified; unrelated optional debt is not automatically a release blocker.
Independent evidence commands continue after nonzero lint/test results to avoid
serial round trips; results never hide a failed command or label the candidate ready.
Build uses uv --offline, no build isolation and a copied source tree; missing existing
setuptools/wheel prerequisites are reported, never installed automatically. A new
staging venv receives only the wheel with --offline --no-deps. After installation,
existing dependency site paths are exposed through a staging-only .pth file. Smoke
checks installed module location and lazy console entry points with native/device
imports and network connection blocked. This is NOT clean-room dependency resolution,
lock reproducibility, active installation replacement or native/GUI acceptance.

No Windows runner execution is claimed in the assistant environment. Harness/syntax/
guard checks are delivery validation only. If an environment prerequisite is missing,
preserve results and classify it; do not upgrade dependencies or change source.

### Decision and remaining-work estimate

**Blocked for expanded R1 release acceptance.** The local ITC targeted evidence gap
is materially reduced, but expanded software/build and native/operator/physical/
deployment evidence remain open, along with exact operating configuration and IDQ
mode requirements. Do not call this sufficient for authorized hardware execution.

The earlier 3-5 estimate applied to a rejected narrower scope and is withdrawn.
No defensible numeric estimate for the expanded release is established yet. The
finite next sequence is: this one offline/build handoff -> one consolidated failure/
configuration triage -> only demonstrated coherent repair batches -> separately
approved workflow/integration acceptance -> deployment. Estimate batch count after
the first results; IDQ histogram evidence, if required, can remain an external blocker.
Do not restart a wrapper-by-wrapper contract/implementation loop or count future
optional features as mandatory. Preserve historical Windows v4 68/12/608 passes and
raw-artifact limitations; no original full-audit/native/operator/hardware acceptance.

Exactly one next task: run/review the expanded offline evidence handoff, then produce
one consolidated blocker batch with actual failure/source references and unresolved
operating inputs. No production changes in this checkpoint. ID900 return instructions
remain intact; no parser work or hardware collection is authorized.

## Decision and current status

**Proposed scope, awaiting maintainer approval. NOT RELEASE-READY.** This is the
single current release-blocker register, not a claim that the whole roadmap is done.
No production, architecture, launcher, wrapper, GUI, schema or dependency change is
made by this checkpoint. The narrower scope is a recommendation, not silent approval
to exclude required safety/physical checks. If the maintainer needs mapping, laser
control or annealing in R1, this estimate must be replaced before proceeding.

Recommended first release: **R1 controlled spectroscopy pilot**: one reviewed HORIBA
configuration/preset on one lab PC, one trained operator and one application process
at a time. Range-spectrum acquisition, existing dark modes/reusable dark workflow,
plotting and exclusive-create result archives/optional CSV/PNG are included only
after the gates below. No laser control, external stage/mirror motion, IDQ, mapping or hazardous workflow
is approved by this proposed scope. This is a controlled pilot, not unrestricted
production certification or approval of every installed entry point.

## Authority and evidence register

Baseline: labtools_source_20261105_135200.txt, created UTC
2026-11-05T13:52:00.8259450Z, HEAD 27745ef08d459864a009a2a41d09ac38174338cf,
branch feature/shared-instrument-session, upstream +8/-0. Tracked worktree/index
recorded clean. Untracked validation artifacts, measurement data, installers,
original contract/implementation backups and lint-fix backup remain present.
This review uses an isolated export, not a live Windows checkout. No Git mutation.

- E1: snapshot Git header and .labtools-itc4000-readback-implementation-v1-backup.json:
  setter guard is committed; all ten installed payloads match the backup. This proves
  payload state, not local acceptance. No local failure output is supplied.
- E2: snapshot lists W1b/readback-contract/readback-implementation lint logs, targeted
  logs/XML, and original source-audit artifacts, but exports no .log/.xml contents.
  File names, hashes and tool versions do not establish their outcomes. Do not invent
  an earlier lint-only run's result or infer later success from commit.
- E3: docs/source-audit-validation.md:24-63 records supplied Windows v4 acceptance:
  core 68, widgets 12, full offline 608; zero recorded failures/errors/skips/timeouts,
  both flags true. Counts overlap. Original raw artifacts and actual v4 evidence
  verification output remain absent. docs/source-comparison-audit.md retains original
  historical-comparison limitations. These are not new failures or a current run.
- E4: current docs/itc4000-readback-contract.md, section Current setter-readback
  implementation, records sandbox baseline 178 and final 195 (55 readback, 96 finite,
  44 lifecycle), zero failures/errors/skips. Ruff was unavailable in that sandbox.
  Do not convert this into Windows acceptance or add it to 608.
- E5: docs/qt-gate-status.md's old 15-pass/4-skip libGL sandbox gate is historical;
  E3 supersedes its claim that the Windows automated gate is still unmet. Visible
  operator/native/physical acceptance remains separate. Later source changes justify
  one candidate regression run, not reopening the historical pass as a failure.
- E6: docs/lab-pc-deployment.md is a proposed manual runbook, not an executed lab-PC
  installation, permission audit, rollback rehearsal or institutional policy.
- E7: current source/test references below establish implemented behavior and test
  coverage source, not new test execution. No application tests/lint were rerun for
  this documentation-only consolidation; delivery checks are reported separately.
- E8: prior report/evidence archive publication was reported failed in the previous
  delivery. This review does not depend on that archive or claim historical delivery.
  The source snapshot and explicit evidence remain authoritative.

## Scope and capability boundary

### Selected real workflow, conditional on approval and acceptance

- Standalone range-spectrum GUI through pyproject.toml:55-59 and
  src/labtools/launchers.py:9-16,27-28; reviewed configuration required by
  gui/spectrum_gui_horiba.py:1126-1141 (LABTOOLS_SPECTRUM_CONFIGURATION_ID).
- Existing spectrum/dark service and archive behavior, not a new acquisition path:
  acquisition/spectrum_service.py:114-235; runtime/spectrum_backend.py:25-109;
  gui/spectrum_gui_horiba.py:809-988; io/spectrum_records.py:17-26,28-84.
- HORIBA internal monochromator/grating/shutter actions used by range/dark capture
  remain part of the selected instrument workflow and require supervised acceptance.
  External motion/shutter tools are excluded; this is not a claim of motion-free optics.
- Only the reviewed detector/configuration is accepted in R1. Existing preset minima
  remain 0.065 s Syncerity and 0.1 s Symphony; no lower override or new calibration
  claim. Device identity, slit/gain/speed/axis and dark compatibility require review.
- Spectrum GUI exposes optional laser controls at :1012-1101. Excluding them is an
  operational pilot boundary, NOT a software interlock or removal. Maintainer must
  approve an effective no-laser-access arrangement and operator procedure. If that
  is not acceptable, R0 remains blocked; do not waive it or silently redesign controls.
- HORIBA ownership in runtime/spectrum_backend.py:13,25-95 is process-local. One
  application process and no competing driver clients is an explicit pilot condition,
  not cross-process exclusion. No shared launcher is required for this scope.

### Existing simulation-only capabilities, not physical acceptance

CLI synthetic intensity-map path (cli.py:47-61; simulation/intensity_map.py) and
schema-version-1 measurement simulation dispatch exist. Hyperspectral GUI offers
only Simulation (gui/hyperspectral_gui.py:39,54-56,108) through labtools gui
hyperspectral, not a real-hardware GUI. These may be used for separately labeled
training; they are not required additions to R1 and do not certify real optics,
counts, timing, motion or native drivers. No universal simulation is promised.

### Explicitly not approved by R1

ITC/laser/TEC control, annealing, IDQ counters/histograms/timestamps, real mapping,
real hyperspectral GUI, standalone motion/camera/shutter tools, multi-window/concurrent hardware,
shared launcher, multi-recipe pipelines, new cryostat/piezo support and compatibility
removal. Existing code/entry points may still be installed; a scoped release is not
technical isolation or a blanket endorsement. R0 must resolve acceptable exposure.
The full project and these additional workflows require their own scoped acceptance.

## Consolidated blocker and evidence matrix

Classification: D = demonstrated source defect/limitation; Q = unresolved design or
scope decision; E = missing acceptance evidence; O = deferred/out-of-scope feature.
Closed findings are retained as evidence, not queued again. All source references
are repository-relative baseline line numbers. No hypothetical defect is asserted.

| ID / class | Workflow and current behavior / evidence | Release impact | Required action and acceptance criterion | Dependency |
| --- | --- | --- | --- | --- |
| R0 / Q | R1 scope is proposed; GUI still exposes laser controls, spectrum_gui_horiba.py:1012-1101; launchers.py:9-16 exposes other tools. | Blocks pilot approval, not proof of a software defect. | Maintainer explicitly approves R1 workflow/preset/configuration, effective excluded-hardware access controls, one-process rule and named operator. If broader scope or technical isolation is required, revise plan before release; no risk waiver. | Maintainer/physical setup review. |
| R1 / E | Current guard committed, ten payloads match (E1); Windows targeted logs/XML listed but absent (E2). | Blocks claiming current local acceptance. | Supply existing raw lint/targeted logs/XML plus exit results/source linkage. Verify counts/errors/skips and actual files; rerun only if absent, stale or failed. Expected delivered targeted selection is 195, not an inferred local pass. | R0 scope; unchanged candidate. |
| R2 / E | Windows v4 68/12/608 passed historically (E3); newer ITC changes/tests postdate it. Old Qt sandbox failures are superseded. | Candidate regression evidence missing; historical pass remains valid for its source. | One current locked-Windows offline regression and relevant lint, including spectrum GUI/service/worker/lifecycle, archives and import isolation. No failures/errors/timeouts; no selected Qt skips; review all full-suite skips/deselections. Do not infer acceptance from runner flags alone. | R1 and current environment. |
| R3 / E | Spectrum fake coverage: test_spectrum_service.py:63-374; test_spectrum_worker_phase4a.py:84-158; test_spectrum_gui_phase1.py:102; test_gui_lifecycle.py:122. Native driver and visible workflow not demonstrated by them. | Blocks real R1 use. | Separately authorized supervised HORIBA acceptance on exact preset/driver: connect/configure/acquire/dark/cancel/close, reviewed units/axis/timing, no competing clients; record driver/model/config and observations. No hardware is run by this plan. | R0, R2; reviewed physical procedure/operator. |
| R4 / E | Archive exclusive-create io/spectrum_records.py:17-26; GUI output naming/export spectrum_gui_horiba.py:957-988; tests/test_spectrum_service.py:186-206,348-374. | No demonstrated overwrite defect for R1; actual operator/data workflow unaccepted. | Visible operator rehearsal: reviewed dark matching, result metadata, NPZ/CSV/PNG, unique local output path, repeated save/no overwrite, cancellation/error display and restart/close. Approve data/backup path; no synced live acquisition directory. | R2; physical portions with R3. |
| R5 / E | pyproject.toml:39-60 build/entry points; tests/test_project_structure.py:26-81,203; lab-pc-deployment.md proposed runbook (E6). | Blocks controlled distribution. | Build candidate wheel; hash/version/commit/lock manifest; non-editable staging install/import/entry-point smoke; no eager native discovery. Lab-PC approved account/permissions, writable data/config separation, shortcut and rollback rehearsal; preserve working install. | R2; final activation after R3/R4. |
| R6 / Q | Process-local HORIBA lock spectrum_backend.py:13,43-44; no cross-process guarantee. | Acceptable only if R0 approves single-process controlled use; not a universal concurrency defect. | Document/enforce operational no-competing-client condition and verify in acceptance. If concurrent use required, separate design needed; do not add launcher opportunistically. | R0/R3. |
| C1 / D closed | ITC finite-input/readback gaps now repaired for recorded scope: devices/itc4000.py:42-88,258-303; finite/readback/lifecycle tests; E4. | Not a new implementation blocker; ITC is outside R1. | Retain checks/tests; R1/R2 evidence still needed. No further ITC micro-task by default. | E1/E4; R1/R2. |
| D1 / D deferred | ID900 get_histogram controller.py:379-415 still eval(raw) at :412. docs/idq-histogram-fixture-readiness.md defers evidence collection. | Open P0, not resolved; no IDQ execution approved in R1. Cannot call whole package universally production-ready. | Preserve return instructions and explicit exclusion. Reopen only with approved fixtures/specification or maintainer reprioritization; if R1 invokes IDQ, stop and rescope. | R0; authentic evidence unavailable. |
| D2 / D deferred | acquisition/intensity_map.py:83-84 and425-428 use timestamp directory mkdir(exist_ok=False); collision can fail rather than allocate another directory. | Demonstrated allocation limitation, NOT demonstrated overwrite/data loss. Mapping excluded from R1. | Defer collision-safe allocation to a mapping release with its tests; do not expand R1 to repair it. | Mapping scope approval. |
| D3 / Q deferred | get_current remains raw float at itc4000.py:295-297; GUI second reads unchanged; enable sequencing/delay/timeout/mutation remain excluded. | Important separate policy questions if laser workflows included, not automatic R1 blockers. | No further refinement now. Review before accepting a laser workflow; no automatic output-off or safety certification. | Future laser scope/physical review. |
| O1 / O | Other wrapper work and physical checks in device-wrapper-audit/repair-plan; SC10/Kinesis historical full-suite notes predate E3. | Not all planned repairs are mandatory for R1. Do not infer every wrapper broken or rerun each historical gate independently. | Current candidate R2 covers regression; classify any actual failure by selected workflow. Separate hardware acceptance for each future included wrapper. | R0/R2. |
| O2 / O | Roadmap phases 6-8 generalization/launcher/simulation/retirement; hyperspectral GUI is simulation-only; recipe dispatch single measurement (measurements/dispatch.py:140-250). | Optional future capability, not proof R1 incomplete. | Keep backlog separate; no new launcher, pipelines, cryostat/piezo or real hyperspectral GUI in this plan. | Future product scope. |
| E9 / E separate | Original historical comparison and v4 raw-artifact evidence command output remain absent (source-comparison-audit.md; E3). | Blocks claiming original full audit independently verified, not a demonstrated R1 runtime failure. | Preserve limitation. Inspect approved existing artifacts when supplied; do not manufacture comparison or demand original-audit completion for unrelated optional features. Current R1 candidate evidence still required. | Supplied historical artifacts. |

## Critical path and finite batches

No unresolved demonstrated production defect was established in the selected
HORIBA-only path by this static consolidation. This is NOT a proof of defect absence.
There is no justified new production patch in this checkpoint.

B1 (next, one evidence checkpoint): **R1 candidate evidence closure**. Obtain explicit
R0 approval, inspect existing raw local logs, then prepare/execute only necessary
current-candidate offline/Qt/lint/build/staging-import checks in the maintainer's
Windows environment. Record HEAD, lock hash, relevant source/test hashes, commands,
exit codes, XML counts/skips, timeouts and candidate wheel hash. Existing
scripts/validate_source_audit.py may provide bounded core/widgets/full evidence,
but its lint/hash list is seven hyperspectral files (:20-27), not the whole candidate.
Its full gate permits skips in the flag logic (:146-155); inspect XML and selected
pilot tests explicitly. Supplement current ITC and pilot-path lint/source linkage.
No hardware discovery, driver diagnostic, physical output or automatic dependency
upgrade. Build/install is into a separate staging environment, not active lab code.
This document does not execute or authorize hardware work.

B2 (conditional, zero to two coherent repair batches): only failures demonstrated
by B1 that block R1, grouped by common root cause. Implement already-decided fixes,
regression tests and concise docs in one handoff. Environment repair is not a source
rewrite. Unrelated optional lint/feature debt does not become a blocker automatically.
A safety/design conflict is escalated, not guessed. Any source change requires
appropriate regression revalidation and a new candidate hash.

B3 (one acceptance checkpoint): separately approved supervised native-driver/physical
and visible-operator R3/R4 session on the frozen candidate. Plan it only after B1/B2;
no native/hardware commands are included here. Preserve working configuration and
record failures/uncertainty. A failed session can require more repair cycles.

B4 (one deployment checkpoint): R5 lab-PC permissions/non-editable installation,
operator shortcut/data paths, rollback rehearsal, release notes/exclusions and signed
maintainer release decision. Staging build preparation can run during B1; activation
waits for B3. No claim that copying a wheel establishes acceptance.

Critical path: R0 -> B1 -> [B2 if demonstrated failures] -> B3 -> B4.
Missing approved hardware/operator availability can block calendar progress regardless
of code iterations. Scope expansion invalidates the sequence/estimate.

## Conditional remaining-work estimate

**Planning estimate: 3-5 further coherent checkpoints after this consolidation**, not
3-5 guaranteed chat messages or a delivery date. Derivation: B1 + zero-to-two B2
batches + B3 + B4. Three is the no-new-defect case; five assumes no more than two
repair batches. Assumptions: R0 accepted as written, existing environment is usable,
required raw evidence can be supplied or safely rerun, one reviewed HORIBA setup and
operator are available, and packaging/physical acceptance reveal no larger defect.

This is a bounded planning recommendation, not a measured project-wide forecast.
More than two repair batches, safety conflicts, unavailable hardware, native-driver
failures or broader scope require a new estimate. Completing the entire roadmap has
no defensible count from this evidence. Do not say the project is ready in three
iterations, or that the P0 is resolved by excluding it from a pilot.

## Stop conditions and completion definition

- Stop on unexpected dirty target/source state, actual lint/test failure, selected
  Qt skips, timeout, missing source linkage or unapproved scope. Preserve artifacts.
- No automatic new wrapper task. A new issue enters the blocker register only with
  evidence, selected-workflow impact and an acceptance criterion.
- R1 is ready only when R0 approved, R1/R2 current software evidence closed, R3/R4
  native/physical/visible acceptance closed and R5 deployment/rollback closed.
  Keep R6 condition explicit and D1/D2/D3/O1/O2 exclusions in release notes.
- Historical Windows automated passes remain historical passes. Current evidence
  gaps are not retroactive failures; native/operator/physical acceptance is never
  inferred from fake tests, screenshots, simulation or installation.

## Exactly one next task

R1 candidate evidence closure (B1), not another implementation micro-task. Ask for
maintainer scope approval if not explicitly supplied, then reconcile actual local
logs/XML and prepare one bounded offline/Qt/build evidence handoff. Do not execute
hardware, alter source/dependencies or add features during that task. If approval or
raw evidence is unavailable, record the exact missing input rather than fabricate
acceptance or another source patch.


## Expanded R1 tooling follow-up, 5 November 2026

The complete expanded-R1 lint inventory contains 44 findings in ten test/support
files. The bounded follow-up changes only those files and this documentation.
No production hardware behavior, acquisition feature, dependency metadata,
backend selection, IDQ counting scope or ID900 histogram deferral is changed.

Original evidence remains historical: accepted ITC 195 cases and remaining
offline 590 cases. Do not add affected reruns to these counts. Source linkage
matched all 143 recorded fingerprints before correction. The original failed
results must remain immutable.

The conftest change is global collection support, not a local test-only impact.
Fifty fake-object hook comparisons preserve marker/permission behavior. Full
590-node and 195-node collection comparison on the original Windows environment
is still required. If either differs, stop reuse and assess broader regressions.
The bounded execution scope is eight edited test modules, 175 cases, plus those
collection checks. Unchanged 415 remaining-offline cases and accepted ITC 195
may be reused only with valid source and collection linkage.

Development validation: 170 non-Qt affected cases passed; a final 69-case rerun
covered subsequent context-header simplification. Five GUI subprocess cases,
full Windows collection and Ruff remain pending. No skipped GUI test is accepted.

Packaging is blocked by unavailable approved build-only backend material.
pyproject.toml already declares setuptools>=69. Do not add duplicate metadata,
change backend, install into acquisition .venv, or choose an unreviewed version.
Supply an approved exact setuptools wheel/version/SHA-256/provenance and all
required hash-pinned build-only wheels. The follow-up runner creates a separate
build-only environment and records versions, commands and resulting wheel hash.
Staging uses a non-editable wheel with explicitly inherited dependency paths;
this is not clean-room dependency, native-SDK, physical, operator or deployment
acceptance. No wheel or staging pass is claimed at this checkpoint.

Next coherent task: run the linked tooling/collection gate on the established
Windows environment, then close only the approved-backend wheel/staging gap.
Do not start another wrapper or acquisition feature task.


### Reconciled tooling delivery v2 (2026-11-05)

The tooling package was rebased onto the current expanded-R1 documentation,
retaining every existing line and the original ten test/support corrections.
The original parent results and its artifact hashes remain authoritative and
immutable. The original 143 source fingerprints are unchanged.
The follow-up section above records historical delivery evidence, not a new
Windows or Qt run. Windows collection/lint/175-case verification remains pending.
The linked runner checks the reconciled documentation as well as source files;
no source-linkage guard is waived. Run verification before committing.
Earlier instructions to rerun the original expanded evidence handoff are
superseded for this checkpoint by the linked tooling follow-up only.
No production code, dependencies, device behavior or ID900 deferral is changed.
Cleanup and archived-backup restoration remain separate from this checkpoint.
Build/staging remains blocked pending reviewed build-only prerequisites.

## Packaging and staged-wheel simulation checkpoint (2026-11-09)

At source HEAD `6074fdad670ed0099c44bbab44c5049aee537c9a`, a clean Git
archive was built outside the repository with `setuptools 84.2.1` in a separate
build environment. The result was `lab_tools-0.1.0-py3-none-any.whl`. The wheel
was installed non-editably into a separate staging environment, and core
`labtools`, `labtools.measurements`, and `labtools.processing.spectrum` imports
resolved from that staged installation.

The staged wheel then completed the existing deterministic intensity-map
simulation with `--points 5 --seed 12345`: all 25 synthetic points completed and
the output was explicitly labelled `SYNTHETIC DATA ONLY`. Output, build and
staging artifacts remained outside the repository. No hardware was accessed and
the acquisition `.venv` was not modified.

Third-party dependencies were inherited read-only from the acquisition `.venv`.
This closes the immediate wheel-build, staged-install, staged-import and synthetic
smoke-test gap only. It is not clean-room dependency, native-SDK, permissions,
operator, physical-hardware, rollback, lab-PC deployment or release acceptance.

