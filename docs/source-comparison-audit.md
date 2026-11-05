# Source audit recovery: current-snapshot findings

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

## Current validation checkpoint v3 (2026-11-02)

Authoritative input: `labtools_source_20261102_121604.txt`, HEAD
`b23c6fd95e0c0027c924f2d1e1f37e76fc5f4cf5`, branch
`feature/shared-instrument-session`, upstream +1/-0; no tracked changes recorded.
Eight v2 recovery files match exactly; two have comment-only, AST-equivalent
changes. Preserve this baseline rather than reverting those edits.

Sandbox core gate: **68 passed, no skips or deselections**, including all four
unchanged import-isolation tests and seven QtCore lifecycle cases. No application
source changes are made by v3. Widget acceptance remains blocked by missing
`libGL.so.1`; the full offline attempt timed out without completion. No lab-PC
acceptance log was supplied. Hardware and the original older-snapshot audit remain
unverified. The earlier recovery sections below are historical evidence.

See [source-audit-validation.md](source-audit-validation.md) for the exact scope,
commands, evidence and remaining gates. Run
`uv run --no-sync python scripts/validate_source_audit.py --gate all` locally and
retain its logs/XML/results.json. Core-only success is not full acceptance.

## Scope and evidence limits

Input: labtools_source_20261102_114759.txt, created UTC
2026-11-02T11:47:59.2340751Z. HEAD cefe007f309bd5389ca7782bce9b9e813c66257e,
branch feature/shared-instrument-session, upstream +0/-0. Snapshot records no
tracked worktree/index changes, but untracked apply_labtools_source_audit.py and
measurement-data/. 257 file sections were reconstructed; trailing-newline metadata
was used. This is an exported working tree, not a complete Git checkout.

The earlier audit prompt, older comparison snapshot and earlier installer's source
were not recovered. Therefore this delivery does NOT claim to complete the
original two-snapshot comparison, reproduce every earlier requested output, or
prove why the original guard rejected five paths. The five refused paths are
present in this snapshot. The original installer is named in Git status but its
contents are absent from the export. Later silent invocations are not evidence of
successful application. No old payload was reused or guard bypassed.

## Confirmed findings and changes

1. Owned-runtime validation cleanup gap, high priority.
   In measurements/hyperspectral.py, runtime.check preceded the try/finally.
   A runtime created by the facade could escape cleanup when check raised.
   Move validation inside the protected region. Use explicit None selection.
2. Primary-error masking, high priority.
   runtime.close in finally could replace acquisition/validation/cancellation
   errors. Preserve the primary BaseException and attach cleanup evidence using
   add_note; propagate cleanup errors normally when there is no primary error.
   Caller-supplied runtimes remain borrowed and are never closed by the facade.
3. Qt terminal boundary, high priority, local Qt validation required.
   HyperspectralWorker.run caught Exception, not asyncio.CancelledError,
   KeyboardInterrupt or SystemExit. Those paths lacked finished/failed signals,
   which are connected to thread.quit. Catch BaseException only at this terminal
   worker boundary and emit failed with a nonempty type-name fallback.
   This deliberately reports process-control exceptions as worker failures.
4. GUI cached-dark mode transition, medium priority, local Qt validation required.
   build_request always forwarded self.dark_record, although request validation
   rejects a dark record outside pre_taken mode. Forward it only in pre_taken.
   Preserve the cached record so returning to pre_taken can reuse it.

## Preserved and deferred

Preserved the latest hyperspectral_view and plotting/click-selection implementation;
no replacement with older source. No changes to physical commands, detector limits,
units, schemas, archive format, scan order, simulation model or real/simulation
selection. No hardware access or Git mutation was performed.

The request owner is validated but is not forwarded into the default
HyperspectralMirrorProvider created by HyperspectralRuntime; it retains its default
owner label. This is a remaining ownership-label contract question, not proof of a
reservation bypass. Review it separately with shared-session concurrency tests.

No claim of repository-wide style consistency or complete lifecycle safety is made.
The review concentrated on hyperspectral facade/runtime/worker/GUI/presentation
and their existing tests, plus checkpoint documentation. Other subsystems were
included in an attempted full offline run but not comprehensively re-audited.

## Validation evidence

Environment: Python 3.12.15, pytest 9.1.1; PyQt6 and Ruff unavailable.
Installed dependencies were not resolved against the project's requested versions.
No hardware was connected or imported intentionally.

- Initial full offline run exceeded a 120-second process limit; incomplete.
- Initial targeted baseline with a five-second per-test timeout: 45 passed,
  four failed by timeout in subprocess-based import-isolation checks.
  These are unresolved environment/test failures, not demonstrated product defects.
- Patched bounded run: 53 passed, one Qt module skipped, four import subprocess
  tests deselected. Includes eight new headless cleanup regressions.
- Replaying new regressions against original facade: four failures were observed
  before an uncaught cleanup KeyboardInterrupt stopped that baseline replay.
  This reproduces the cleanup gaps; it is not a complete baseline test result.
- New Qt worker and dark-selection tests are supplied but NOT executed here.
- Ruff, complete offline suite, Qt acceptance and hardware acceptance remain open.

## Local acceptance

Use the replacement installer only. Its check accepts only exported baseline or
exact delivered text, with UTF-8 BOM and CRLF/LF normalization. verify requires all
changed files to be delivered. It also guards unchanged hyperspectral runtime and
presentation source. Apply backs up exact original bytes; rollback refuses later
edits. No force option exists. Keep the backup until acceptance is complete.

Run the supplied PowerShell acceptance script. A missing PyQt6 or Ruff dependency
must fail acceptance, not silently count skipped tests as Qt validation. Do not
commit this checkpoint as fully accepted until those gates pass locally.
