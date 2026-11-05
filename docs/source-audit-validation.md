# Source-audit validation checkpoint v3

## Owner-label contract decision checkpoint (2026-11-05)

This later checkpoint characterizes owner labels; it does not reopen or replace
v4's recorded Windows acceptance. See [owner-label decision](hyperspectral-owner-contract.md).
Decision: reservation labels remain provider/runtime-owned diagnostics. The
validated, recipe-serialized request label does not automatically override a
provider. No owner propagation or production behavior change is implemented.

Authority: `labtools_source_20261105_111524.txt`, HEAD
`1bdef873daaa94e84e0455eb1e80b73d9a330a77`, branch
`feature/shared-instrument-session`, clean tracked worktree/index, upstream +1/-0.
The actual v4 evidence-command output and raw logs/XML remain absent from this
export; local raw-artifact verification is not claimed.

Validation: 60 targeted offline cases passed (26 new characterization cases),
zero failures/errors/skips. Ruff could not execute: the sandbox has no `ruff`
module. Local lint remains required; no dependencies were installed. Production
source, existing tests, runner, schemas, limits and backend selection are unchanged.
The v4 sections below are historical closure records, including their old next-step
instructions; this section supersedes only their deferred owner-label question.

## Current closure checkpoint v4: recorded Windows acceptance (2026-11-05)

**The remaining widget and full-offline gates passed in the supplied Windows run.**
This supersedes the open-gate status in the historical v3/recovery sections below;
it does not convert those earlier sandbox failures into passes.

Authoritative snapshot: `labtools_source_20261105_074708.txt`, created UTC
2026-11-05T07:47:08.2392102Z. HEAD
`0ce76d7ce8c81ab01ab9d61daddc39a606c77185`, branch
`feature/shared-instrument-session`, upstream +2/-0. No tracked/staged changes are
recorded. Preserve the untracked v2/v3 backups, v3 installer, validation directory
and measurement-data.

Evidence: `.labtools-validation/source-audit-20261105T074324574893Z/results.json`.
The runner requested `all`; lint and both prerequisites passed; core **68 passed**,
widgets **12 passed**, full offline **608 passed**. Each test gate records zero
failures/errors/skips; every process returned 0 with `timed_out: false`.
`all_gates_passed` and `requested_gates_passed` are true. Counts overlap and must
not be summed. The full gate used `-m "not hardware"`; deselection totals are not
recorded in the JSON and are not inferred to be zero.

All seven recorded source SHA-256 values match the exported current files exactly
as UTF-8/LF bytes, including the runner. All nine v3 delivered files match the
embedded v3 backup's installed text. This establishes evidence-to-source linkage,
not a new test execution in this assistant environment.

The raw logs/XML are listed with hashes/sizes but their contents are NOT included
as snapshot file sections. Their counts are available through the runner's JSON;
independent raw-log/XML review was not performed here. The standalone v4 installer
provides a read-only `evidence` command to verify those exact artifacts locally,
compare XML counts and confirm the seven source hashes. Do not invent absent log
contents or treat a missing artifact as success.

This checkpoint changes documentation only. Production code, tests, validation
runner, plotting/click selection, raw-sum/mask semantics, immutable results,
archive/schema versions, limits, dependencies and hardware commands are unchanged.
No additional application correction was justified. The widget gate exercised
cached-dark transitions and delayed-cleanup close/restart refusal; the core gate
includes repeated terminal failures, immediate cancellation, borrowed ownership
and the four unchanged import-isolation tests.

The bounded offline recovery acceptance is closed for this recorded Windows run.
Hardware/native-SDK physical acceptance, visible operator acceptance beyond these
automated tests, request.owner/provider-label review and the original pre-audit
comparison remain outside this closure. The original earlier comparison inputs
were not supplied; no missing requirements are invented. Do not begin a new
feature/architecture phase as part of this checkpoint.

### Next bounded continuation

Verify the original ten evidence artifacts locally with the v4 `evidence` command,
retain the results/logs/XML and commit only the six documentation paths after
review. If artifact hashes/XML disagree, reopen evidence reconciliation only.
Do not rerun old v2/v3 rollback against this later documentation state. The v4
backup is separate and exact-byte rollback refuses later edits.

---

## Historical checkpoint record (not current gate status)

## Authoritative input and local-evidence boundary

Snapshot: labtools_source_20261102_121604.txt, created UTC
2026-11-02T12:16:04.4008472Z. Branch feature/shared-instrument-session,
HEAD b23c6fd95e0c0027c924f2d1e1f37e76fc5f4cf5, upstream +1/-0.
The export records no tracked worktree/index changes. Untracked paths are
.labtools-source-audit-v2-backup.json and measurement-data/ (two simulation runs).
261 file sections were reconstructed with the exported trailing-newline metadata.

No Windows validation transcript or results.json was supplied. Neither the original
apply_labtools_source_audit.py nor validate_labtools_source_audit_v2.py is included
as a file section in this export. The earlier assistant's v2 installer/validator
artifacts remain available in this conversation and were inspected, but they are
not evidence of which bytes ran on the lab PC. No local acceptance is inferred
from the new commit or the backup file.

## Ten-file recovery comparison

Eight files exactly match the delivered v2 text after UTF-8 BOM/CRLF normalization:
- docs/ai-handover.md
- docs/architecture.md
- docs/refactor-roadmap.md
- docs/scripted-measurements.md
- docs/source-comparison-audit.md
- src/labtools/gui/hyperspectral_controller.py
- src/labtools/gui/hyperspectral_gui.py
- tests/test_audit_hyperspectral_regressions.py

Two files differ only in removed noqa comments:
- src/labtools/measurements/hyperspectral.py: two BaseException annotations removed.
- tests/test_audit_hyperspectral_worker.py: four E402 annotations removed.

Both changed Python files have identical parsed ASTs to the delivered v2 versions.
These edits are preserved, not reverted. Exact-text v2 verification therefore is
not an acceptance route for this current baseline. v3 guards the fresh exported
text explicitly; it does not weaken or bypass v2 guards.

The 11:47:59 snapshot is also available in this conversation. Comparison of the
recovery paths confirms the three source fixes and recovery docs/tests are present
in the 12:16:04 snapshot, with the comment-only differences above. This is not the
original pre-audit two-snapshot comparison: the original earlier prompt and its
older comparison baseline remain unavailable. No missing requirements are invented.

## This delivery

No production source changes were justified by the executed tests. All src/ files,
including hyperspectral plotting/click selection, facade, runtime, acquisition,
configurations and device wrappers, are unchanged from the authoritative snapshot.
No dependency policy, lockfile, schemas, limits, hardware behavior or Git state was
changed. The request.owner/provider-label question remains deferred.

Added tests/test_audit_hyperspectral_lifecycle.py: QtCore event-loop tests for four
failure types (ordinary exception, CancelledError, KeyboardInterrupt, SystemExit),
three repeated acquisitions per failure type, exactly one terminal signal then
idle, immediate repeated cancellation, delayed cleanup retaining busy ownership,
concurrent-start refusal, and borrowed runtime forwarding without controller close.

Expanded tests/test_audit_hyperspectral_worker.py with cached-dark mode round trips
(none/fresh/pre_taken) and close-during-cleanup/restart-refusal tests. These widget
regressions are supplied but have NOT executed successfully in this environment.

Added scripts/validate_source_audit.py: repository-local lint/core/widgets/full gates,
explicit prerequisite probes, bounded subprocesses, targeted-skip rejection,
stdout/stderr logs, pytest XML, source hashes, environment versions and results.json.
A core-only pass explicitly does not set all_gates_passed. It does not install
packages or mutate Git. Logs default to .labtools-validation/source-audit-<UTC>/.
The Windows taskkill timeout path is supplied but was not executed on Linux.

## Executed evidence (sandbox, not the lab PC)

- Existing five recovery Python files: Ruff passed.
- Core runner gate: 68 passed, 0 failures, 0 errors, 0 skips; no deselection.
  Includes all four original subprocess import-isolation assertions unchanged.
- Separate import-isolation diagnostic: 4 passed, 43 deselected by the diagnostic
  selection expression. No assertion was removed or weakened.
- Earlier small QtCore/cleanup/presentation run: 21 passed. This overlaps the 68;
  these counts must NOT be added together.
- Widget prerequisite probe: failed with ImportError for missing libGL.so.1.
  Earlier Qt installation attempts also exposed a missing sip component before
  the isolated sandbox environment was repaired. These are environment failures,
  not demonstrated application defects. QtCore is usable; QtWidgets is not.
- Full offline attempt without the isolated Qt package path: exceeded a 110-second
  outer process limit, exit 124, with no final pytest summary. It is NOT a pass.
- A direct faulthandler import diagnostic produced a truncated _path_stat traceback
  and segmentation fault. It does not establish an application deadlock or root
  cause; the unchanged import-isolation tests subsequently completed successfully.

The prior five-second per-test import deadline was too short for these observed
sandbox runs. The four tests passed with a twelve-second diagnostic deadline and
again without per-test overrides inside the bounded core gate. This establishes
completion in these runs, not a universal import-performance guarantee. No import
code was changed and no isolation assertion was deleted.

### Exact principal commands

From the reconstructed repository, with the isolated sandbox PyQt6/Ruff directory
on PYTHONPATH and QT_QPA_PLATFORM=offscreen:

    python scripts/validate_source_audit.py --gate core --output /mnt/data/v3_core_evidence

Core child command (as logged):

    python -m pytest -q --junitxml=/mnt/data/v3_core_evidence/core.xml tests/test_audit_hyperspectral_regressions.py tests/test_audit_hyperspectral_lifecycle.py tests/test_hyperspectral_service.py tests/test_hyperspectral_failure_matrix.py tests/test_hyperspectral_view.py tests/test_hyperspectral_presentation_interaction.py tests/test_measurements_hyperspectral.py tests/test_measurements_hyperspectral_contract.py

Import diagnostic:

    python -m pytest -q --timeout=12 tests/test_hyperspectral_service.py tests/test_hyperspectral_failure_matrix.py tests/test_measurements_hyperspectral.py tests/test_measurements_hyperspectral_contract.py -k "import_isolation or fresh_process or clean_process"

Widget probe:

    python -c "import PyQt6.QtWidgets"

Full attempt (without isolated Qt path):

    timeout 110 python -m pytest -q --timeout=12 -m "not hardware"

## Remaining acceptance and next boundary

Run the v3 installer check/apply/verify, then use the existing labtools environment:

    uv run --no-sync python scripts/validate_source_audit.py --gate all

Keep the generated results.json, XML and logs, including failures. A prerequisite
failure, targeted skip, nonzero test exit or process timeout is not acceptance.
Widget dark switching and close-during-cleanup remain open until those actual
widget tests pass. Full offline completion remains open. Hardware acceptance is
not performed and is outside this checkpoint. The original audit comparison also
remains incomplete for lack of its earlier inputs.

Do not rerun the v2 rollback after this checkpoint: its backup belongs to an older
state. v3 uses its own exact-byte backup and refuses later edits. Preserve both
backups and measurement-data; stage only the explicit checkpoint paths after local
acceptance. Never use git add . for this delivery.
