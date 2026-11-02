# Source audit recovery: current-snapshot findings

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
