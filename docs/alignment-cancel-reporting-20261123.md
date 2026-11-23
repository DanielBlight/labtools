# Alignment cancellation cleanup reporting, 2026-11-23

Status: evidence-only follow-up; Windows Qt and hardware acceptance pending.

The supplied Windows run passed 16 tests before the disconnect-failure case failed
because the GUI said Stopped rather than requiring teardown. The preceding assertion
that the worker is faulted passed. The earlier capture timeout no longer occurred.

Cause: cancellation is intentionally preserved as the primary exception when
cleanup also fails. The fake and real adapter attach cleanup-failure information;
the worker uses that information to enter faulted state. The GUI's unconditional
CancelledError -> Stopped branch ignored this distinction. This was an omission
in the original GUI error path, not an incorrect test expectation.

Correction: on cancellation, inspect the completed worker state. Clean cancellation
still displays Stopped. Faulted cancellation uses the same error-reporting helper
as other job failures, showing the teardown requirement and detailed traceback.
The helper preserves suppression of modal dialogs during pending window close.
Worker cancellation semantics, ownership, real timing and test assertions are unchanged.
The helper is reusable when the window is integrated into the unified GUI.

Validation: six Qt-free cases execute the actual GUI completion/helper method ASTs
with stub job, worker and dialog boundaries. Cases cover clean Stop, cancelled
cleanup failure, close during cancelled cleanup failure, ordinary failure with/without
close, and normal completion. All six pass. Available Ruff 0.11.13 passes for the
GUI module and new regression module. This is branch-level validation, not Qt widget,
Windows rendering, full-suite or connected-hardware acceptance. The local GUI method
was reconstructed from the supplied source and previously delivered stream edit;
the updater checks the affected method AST before changing the current checkout.
Updater preflight/apply/idempotence/rollback were tested in a temporary Git checkout.

## Next bounded continuation prompt

Read the latest Windows result after cancellation-cleanup reporting is corrected.
Run the window lifecycle module and new reporting tests, then the full targeted
selection. Preserve the faulted-worker assertion and teardown message; do not turn
failed disconnect into a clean Stop or weaken modal-close coverage. If a failure
remains, inspect that exact branch rather than extending timeouts. Once targeted
validation passes, consolidate the original repair and all follow-ups in one source
checkpoint with actual results and exact staging commands. Then record connected
Start/multiple-frames/Stop/restart acceptance before unified-workspace integration.
Keep detector minima, real timing, ownership through teardown and flat profiles intact.
