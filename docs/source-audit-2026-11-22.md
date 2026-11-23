# LabTools source audit and persistent-alignment repair

Status: evidence-only engineering audit, 2026-11-22. Not release approval.

## 1. Scope and provenance

Supplied baseline: `54ce3563385734f49be567e27530562a14c64014`, branch
`fix/alignment-persistent-session-v2`. The manifest reports a clean index/worktree.
The exported repository path is still the OneDrive checkout; that does not prove
where the maintainer's current development checkout or installed application lives.

Inputs:

- `labtools_full_project_20261120T221923-manifest.txt`
- `labtools_full_project_20261120T221923-part-001.txt`
- `labtools_quick_snapshot_20261120T221940.txt`

All 384 full-bundle entries were decoded and their declared byte sizes and SHA-256
hashes verified. This is a source snapshot, not a Git object database, wheel,
Windows environment, instrument connection or current remote-branch view.

Review coverage: static documentation inventory and local-link scan across all 80
supplied project Markdown files (root README, changelog, contributing guide and
`docs/**/*.md`); detailed reconciliation of document-status, release-plan, changelog,
current-state, README/index, handover/architecture, acceptance records, alignment
references and the profile proposal. Relevant service, worker, adapter, GUI and
workspace ownership code was inspected. This is not a line-by-line correctness
proof of every device, every historical document, or every vendor file.

No local Markdown file targets were missing in that 80-document scan. External
URLs and heading-anchor validity were not checked. Link validity does not establish
that linked instructions are current. See the accompanying documentation inventory.

## 2. Executive conclusion

The observed reconnect-per-spectrum behaviour is directly explained by the source:
the GUI submitted `acquire_alignment` repeatedly; each service call entered and
exited the real alignment backend. Every frame therefore connected, configured,
moved and disconnected. A persistent worker thread alone did not make the device
session persistent.

The repair moves repetition inside one service operation and one worker job. The
GUI receives immutable latest-frame results without owning a native device. This
is suitable as the backend contract for later unified-GUI integration. The unified
workspace itself has not been changed to embed alignment in this patch.

The documentation has drifted behind both implementation and lab observations.
Several files call themselves the current authority while prescribing incompatible
scope or next tasks. The update reconciles the entry points without deleting old
hardware evidence or declaring a new release.

## 3. Findings and dispositions

### A01: reconnect-per-frame defect [high, repaired in source]

Evidence: `src/labtools/gui/alignment_gui_horiba.py` `_submit`/`_poll_job`,
`src/labtools/acquisition/spectrum_service.py` `acquire_alignment`, and
`src/labtools/runtime/spectrum_backend.py` `open_real_alignment` in the input.
The lab-PC record explicitly reports this failure on 2026-11-20.

Change: add `SpectrumService.run_alignment`, `SpectrumWorker.start_alignment`,
`AlignmentStreamJob.take_latest`; submit once from the GUI. One backend context
owns all captures and teardown. Keep the existing single-frame APIs unchanged.

Acceptance remaining: Windows Qt lifecycle and connected HORIBA Start/Stop/restart.
Do not mark the historical hardware FAIL as resolved from fake-backend tests alone.

### A02: gaps in operation ownership [high, repaired in source]

Per-frame jobs released the worker between frames. The real range adapter used
`_REAL_RANGE_OWNERSHIP`, while the real alignment adapter did not. A second worker
could therefore bypass the alignment worker's own busy state.

Change: keep the worker busy throughout the continuous run and cleanup. Make the
alignment adapter use the same process-local guard as the range adapter. Acquire
before native construction; release even if construction, connect or disconnect
fails. Preserve existing primary-error/cleanup-failure handling.

Limit: direct wrapper clients and other processes are not covered. The lock is
exclusion, not a shared connection cache or proof that a failed device is recovered.

### A03: unbounded frame delivery would create UI backlog [design risk, avoided]

Change: a lock-protected single-slot latest-frame mailbox. Worker publishes immutable
results, Qt polls them, and older undisplayed frames are replaced. Acquired sequence
numbers can skip on screen. This is deliberately not lossless recording. No native
objects, Qt widgets or callbacks into widgets cross the worker boundary.

### A04: previous working main implementation [evidence limitation, recorded]

`docs/history/horiba-alignment-v2-archive.md` identifies:

- branch `archive/horiba-alignment-v2`
- tag `archive-horiba-alignment-v2`
- commit `9024b3adbd132bfb3db7ea8b83a803ffbd98f915`

The old implementation is not present in the supplied export and cannot be inspected
with `git show` here. No historical code comparison or direct restoration is claimed.
Its archive note documents the useful continuous workflow and a separate lifecycle
that should not be reintroduced. Its 0.02 s exposure override is not adopted.

If a later visual comparison is needed, use the named branch/tag first and inspect
its tree before assuming that every newer runtime file existed in that commit:

```powershell
git ls-tree -r --name-only archive/horiba-alignment-v2 -- src/labtools
git show archive/horiba-alignment-v2:src/labtools/gui/alignment_gui_horiba.py
```

Do not make historical-source retrieval a prerequisite for testing this bounded
lifecycle repair, whose cause is visible in the supplied current source.

### A05: unified GUI is not already on one spectrum-worker path [high integration risk]

`gui/workspace_panels.py` `OwnedSpectrumPanel` wraps `HoribaRangeWindow` and uses
workspace reservations. The standalone alignment window and scripted spectrum
runtime construct SpectrumWorkers separately. It would be inaccurate to describe
all current GUI operations as one shared-worker implementation.

Disposition: document the explicit integration contract in `horiba-alignment.md`.
Next integration must bridge/compose application ownership, Stop all and deferred
close, holding the workspace lease through stream teardown. Do not embed another
private worker and assume shared hardware ownership follows automatically.
No broad workspace/controller rewrite is included in this repair.

### D01: conflicting documentation authority [high, entry points corrected]

`document-status.md` names current-state/release-plan as current authorities, but
`ai-handover.md` still calls an older HORIBA-only R1 readiness record the single
current register. `docs/README.md` calls the older roadmap canonical. Architecture
opens with a 2026-11-05 next-wrapper task that is no longer the current milestone.

Change: current routing notes in document-status, handover and architecture;
README/index route to current-state and release-plan. Historical records remain
intact and explicitly subordinate. Release-plan's "three authoritative documents"
now means three release-decision documents, not the removal of technical references.

Remaining cleanup: split mixed architecture/history and archive older plans with
link updates in a dedicated documentation-only change, not during hardware repair.

### D02: current-state version is wrong [medium, corrected]

Input current-state says the installed project remains `0.1.0`, while pyproject and
wheel-smoke expectations say `0.2.0rc1`. The export cannot establish today's installed
version on either PC. Corrected to source metadata and an explicit installed-state
limitation. The lab record's "RC2 profile freeze" is not a package-version increment.

### D03: release plan lists completed source work as future work [medium, reconciled]

CI definition, changelog, release notes, version assignment, exporters and optional
research extras already exist. Several Gate 0 removals are already reflected in the
snapshot. Added a gate-status table separating present source from missing evidence.
The original required-work lists remain gate definitions, not an instruction to
reimplement completed work. Old milestone estimates are labelled historical.

### D04: hardware evidence is not reflected in the summary [high, reconciled]

The 2026-11-20 lab-PC records include camera and spectrum observations, corrected
ITC4000 shutdown behaviour, map orchestration, Annealing dry-run/cancellation and a
minimal powered pass. The later record also says IDQ nonzero counts are pending
and alignment lifecycle failed. Current-state and release-plan now link and summarize
these bounded observations. No complete device row is promoted to PASS.

These records refer to several earlier commits and do not establish that every
matrix cell, fault mode, maximum-open-time behaviour, power-loss recovery or packaged
candidate rehearsal passed. Preserve the append-only evidence and its provenance.

### D05: changelog mixes plans and completed changes [medium, corrected]

Unreleased previously contained only planned work. Added repair/ownership changes
and validation limitations under Unreleased, without changing the historical
`0.2.0-rc.1` entry or inventing a release date/version. Corrected optional dependency
wording: analysis, notebooks and Napari extras already exist. The historical 1,206
Windows passes are retained as a recorded baseline, not this repair's test count.

### D06: root README denies implemented simulation [medium, corrected]

README said only map components were synthetic and that camera/spectrometer
simulation did not exist. Current source includes explicit spectrum/alignment,
synthetic camera and workspace simulation. Replaced the blanket denial with scoped
workflow simulation language, without claiming complete physical-device emulation.

### D07: unified instrument-profile proposal is buried [medium, discoverability fixed]

The proposal exists in `docs/next-recommendations.md`, below a historical preamble.
It is not missing, but was easy to overlook in a new review. Linked it from current
state, release-plan, document-status and handover and labelled it a retained proposal.

Current `InstrumentProfile` is a strict flat dataclass; its loader rejects unknown
fields. No ad hoc spectrometer/ITC fields were added. Versioned subsystem profiles,
identity checks, migration/backward compatibility and removal of lab-specific GUI
constants remain separately planned. The lab's 0.040 A policy and existing profile
approval/identity semantics are not changed here.

### D08: migration-retention instructions conflict [medium, decision remains open]

Repository-hygiene says `.labtools-migrations/` is deliberately retained pending a
decision; operator-workspace says historical migration backups should stay out of
Git. The export contains no such directory entries. It does not expose Git history
or prove all local recovery material is absent. Flagged the conflict rather than
silently deleting files or changing the retention policy. Decide tracked historical
evidence versus ignored local backups explicitly before closing Gate 0.

### D09: duplicate acceptance records [low, retain for now]

Two similarly named lab-PC records overlap; the later record accumulates additional
acceptance and failure observations. Do not merge/delete evidence automatically.
A later index can identify the authoritative chronological continuation while
preserving original commit identities and hashes.

### Q01: full-tree lint is not green in this environment [release evidence gap]

Ruff 0.11.13 (not the locked project version, which requests >=0.16.3) reports exactly
44 findings on both original and repaired `src tests`: 7 E402, 3 E701, 1 E702,
32 F811 and 1 E731. The normalized findings match before and after the patch.
The six changed/new Python files pass the same available Ruff check.

Locations: GUI compatibility imports in intensity_map_gui/laser_anneal_gui;
measurements/__init__.py import layout; compact statements in
`test_hyperspectral_presentation_interaction.py`; imported `wrapper` fixture names
shadowed by test arguments in two ITC contract modules; a lambda assignment in
`test_spectrum_service.py`. The F811 findings are fixture re-export/shadowing
patterns, not evidence that 32 production functions were duplicated.

Disposition: record rather than fix unrelated modules in this repair. Reproduce
with locked Ruff on Windows, then make one focused hygiene commit or document narrow,
justified fixture-import handling. Do not claim hosted CI or whole-tree lint passed.

### Q02: Qt fixture makes non-Qt tests depend on graphics [medium cleanup]

`tests/conftest.py` has a session-autouse QApplication fixture. It prevents even
Qt-free service tests running in this Linux container, where PyQt6 imports fail
because `libGL.so.1` is unavailable. For this audit, six Qt-free modules were copied
unchanged into an isolated test directory with the source import path preserved.
No project conftest was changed and no fake QApplication was substituted.

Recommendation: scope the keep-alive fixture to Qt tests or a dedicated Qt subtree,
while preserving its fix for QApplication lifetime across lifecycle tests. Do not
remove it blindly and reintroduce the earlier Qt lifetime failures.

### Q03: IDQ histogram parser still evaluates response text [high, unchanged]

`src/labtools/devices/idq_time_controller/controller.py` uses
`np.array(eval(raw), dtype=np.int64)` in the histogram response path. This executes
response text as Python and is an unsafe parser boundary. The existing documentation
already defers a format-correct replacement pending authentic, provenance-bearing
response fixtures. No speculative parser replacement is made in this alignment patch.

Keep the histogram path excluded from supported pilot scope until the parser is
repaired and validated, or record an explicit maintainer decision. This does not
mean all IDQ counter paths use this parser; count-input acceptance is a separate gap.
Do not invent a response grammar or treat deferral as risk acceptance.

### Q04: packaging/deployment evidence remains incomplete [release gap]

Source has validation scripts, CI and a no-dependency wheel smoke. That smoke proves
metadata/import isolation, not a complete functional operator environment. No hosted
CI run, newly built wheel, fresh Windows functional install or rollback rehearsal
was performed here. Licence/notices files remain absent in this export; vendor
provenance/redistribution decisions remain outstanding. No legal approval is inferred.

### Q05: export ignore patterns miss the supplied naming scheme [low cleanup]

`.gitignore` includes `labtools_full_project-*.txt`, but supplied exports use
`labtools_full_project_...` and `labtools_quick_snapshot_...`. These are different
patterns. Recommend explicit underscore-based ignore entries and verify with
`git check-ignore` before the next export. Not changed here to avoid expanding
source repair scope into unrelated hygiene policy.

## 4. Prioritized cleanup register

1. **Before candidate approval:** Windows locked lint/full-suite result, connected
   alignment lifecycle, IDQ count evidence, explicit supported/excluded scope,
   package/rollback evidence, licence/notices decision and histogram-path exclusion.
2. **Next bounded GUI integration:** compose the alignment stream with the existing
   workspace ownership/Stop all/close contract. Reuse backend work, do not restore
   parallel native ownership from the archived standalone GUI.
3. **One hygiene change:** reconcile the 44 lint findings with locked Ruff, fix export
   ignores, classify Qt fixtures and resolve migration-retention policy. Keep these
   separate from hardware-command changes.
4. **Documentation-only consolidation:** split historical checkpoints out of mixed
   architecture/handover, reduce duplicated index sections, add a chronological
   acceptance index. Preserve hashes, commit references and working links.
5. **Post-acceptance profile migration:** versioned subsystem schema, compatibility
   loader, identity validation and reviewed limits. Do not change the flat profile
   in place or reset lab acceptance by silently changing configuration semantics.
6. **Later structural cleanup:** decompose large GUI modules and remove legacy-widget
   reparenting only behind stable ownership tests. Input module sizes include
   intensity_map_gui 1,721 lines, spectrum_gui_horiba 1,184, workspace_studio 996,
   laser_anneal_gui 751. Size is a maintenance signal, not proof of a defect.
7. **Packaging refinement:** decide instrument/GUI extras based on actual operator
   installation needs; do not make optional SDKs mandatory by accident or break the
   frozen environment while changing dependency groups.

No bulk deletion, broad GUI rewrite, hardware command change, detector-limit change,
profile migration, version bump or fabricated acceptance was performed.

## 5. Validation actually executed

Environment: Linux, Python 3.12.16, available NumPy/pytest, Ruff 0.11.13. Not the
project's locked Windows runtime. PyQt6 6.7.1 could be installed but cannot load
QtWidgets because `libGL.so.1` is absent. System library installation was unavailable.

- Full-bundle decoding: 384 entries, declared sizes/hashes verified.
- Static Markdown file-target scan: 80 supplied project documents, no missing local
  file targets. External URLs/anchors and vendor docs were not included.
- Six changed/new Python files: Ruff check with `--fix` passed; no unsafe fixes.
- `compileall` over source/tests: passed in the audit environment.
- Guarded updater: preflight, conflicting-edit refusal, exact applied bytes, repeat
  application/idempotence and rollback tested successfully in a temporary Git checkout.
- Six Qt-free regression modules: **119 passed**, no skips/failures in the successful
  isolated run. Includes eight new persistent-session tests, the existing service,
  worker, one-frame alignment, blocked-lifecycle and fake-HORIBA wrapper tests.
- Full-tree available-Ruff result: 44 findings, identical to the original snapshot.
- Standard in-repository test attempts: blocked by the autouse Qt fixture's graphics
  import. These failed setup attempts are not counted as successful tests.
- Qt window tests: not executed successfully. The updated disconnect-failure test
  now requests Stop before expecting stream teardown; a new multi-frame/one-backend
  GUI test was added for Windows execution.
- Full non-hardware suite, locked Ruff, build/wheel smoke, historical Git comparison,
  Windows UI, physical hardware and rollback: not established here.

The successful isolated selection comprised:

- `test_alignment_persistent_session.py`
- `test_alignment_spectrum.py`
- `test_alignment_lifecycle_acceptance.py`
- `test_spectrum_service.py`
- `test_spectrum_worker_phase4a.py`
- `test_horiba_wrapper_lifecycle.py`

They were copied unchanged to `/tmp/nonqt`, with `PYTHONPATH` pointing to repaired
`src` and `/tmp/src` pointing to that source for the existing subprocess isolation
test. Command: `python -m pytest -q --confcutdir=/tmp/nonqt /tmp/nonqt`.
This workaround deliberately omits only the project-level Qt/hardware fixtures for
these known Qt-free tests. It is not a substitute for the Windows release gate.

## 6. Practical Windows continuation

Apply the guarded installer to the checkout matching the supplied baseline. It
checks every target file before changing anything, keeps ignored backups, supports
rollback and never stages, commits, launches hardware or runs long tests itself.
Stop running GUIs before replacing files. Review `git diff --stat` after installation.

Run targeted validation first, using the existing locked development environment:

```powershell
uv run --no-sync ruff check --fix src/labtools/acquisition/spectrum_service.py src/labtools/runtime/spectrum_worker.py src/labtools/runtime/spectrum_backend.py src/labtools/gui/alignment_gui_horiba.py tests/test_alignment_persistent_session.py tests/test_alignment_window_acceptance.py
uv run --no-sync python -m pytest -q -ra tests/test_alignment_persistent_session.py tests/test_alignment_spectrum.py tests/test_alignment_lifecycle_acceptance.py tests/test_alignment_gui.py tests/test_alignment_window_acceptance.py tests/test_spectrum_service.py tests/test_spectrum_worker_phase4a.py tests/test_horiba_wrapper_lifecycle.py
```

Then use the normal full release validation on a clean committed candidate; do not
claim the historical 1,206 count as the result. If whole-tree lint fails, compare
with Q01 rather than attributing every pre-existing finding to this repair.

## 7. Next bounded continuation prompt

Continue from the applied persistent-alignment repair. Read current-state,
release-plan, document-status, this audit and horiba-alignment before editing.
Inspect actual Git status/HEAD and the supplied Windows targeted results. Do not
repeat unchanged wrapper audits. First close any real failure in the targeted
alignment/Qt tests, then obtain one connected Start/multiple-frames/Stop/restart
lifecycle observation. Preserve detector minima, fresh-dark ordering, cleanup/fault
semantics and the one-frame scripted API. Do not declare the earlier hardware FAIL
closed without the connected result. Once accepted, implement alignment in the
unified workspace as one coherent change: compose the existing spectrum runtime or
bridge workspace ownership, hold its lease through stream teardown, use the bounded
latest-frame API, and wire Stop all/deferred close without a second native session.
Add ownership and close regression tests. Keep the strict flat instrument profile
unchanged; its versioned migration is a separate planned task. If comparing the old
GUI, retrieve the documented archive tree first rather than assuming newer runtime
paths existed. Deliver one guarded updater, actual test evidence, exact Git staging/
commit commands and the next bounded prompt. No broad GUI rewrite, speculative IDQ
parser, unrelated lint sweep, invented pass counts or new approval gates.
