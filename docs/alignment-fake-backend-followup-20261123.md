# Fake alignment backend follow-up, 2026-11-23

Status: evidence-only, not Windows GUI or hardware acceptance.

The supplied Windows selection stopped with 33 passed and one failure in
`test_fault_disables_restart_only_after_cleanup[disconnect]`, waiting for a
first displayed frame. The preceding simulation-only repair did not address
`BlockedBackend`, which deliberately uses a real-mode worker to test faults.

Confirmed source issue: after `release` is set, `BlockedBackend.capture` awaits
an already-satisfied event and returns immediately. Continuous captures can then
spin on the worker thread and compete with Qt. A direct coroutine probe confirmed
that a released capture did not yield to another ready task. This is a confirmed
test-double defect and a plausible contributor to the timeout, not proof that
all Windows GUI timing issues are resolved.

Correction: add a 1 ms asyncio wait inside the fake capture, after its release
barrier. It is a scheduling point, not a physical detector timing model or a
real-time deadline. No production code, real acquisition delay, GUI deadline,
assertion, ownership boundary or disconnect-failure injection is changed.
A new regression requires released fake capture to yield to another ready task.
The fake's blocked capture and cleanup barriers remain available to the tests.

Local validation: the probe changes from False to True; the lifecycle module
including the new regression passes 8 tests in an isolated Qt-free run. Available
Ruff 0.11.13 check --fix passes. Windows Qt and the full targeted run remain pending.
The updater's preflight, apply, idempotence, conflict refusal and rollback were
tested in a temporary Git checkout.

Apply the new updater on top of both earlier repairs; do not rerun old installers.
It modifies only the fake-backend test module and adds this evidence note. The
first pacing repair correctly preserved real-mode acquisition timing, but should
also have inspected the fake real-mode capture path. This follow-up closes that
omission without adding a delay to production real acquisition.

## Next bounded continuation prompt

Inspect the Windows result after the fake-backend scheduling correction. Run the
alignment window acceptance module, then the existing full targeted selection.
Do not increase deadlines, skip disconnect-failure coverage or throttle production
real acquisition. If a failure remains, inspect its exact assertion and current
worker/job state before editing. Once the targeted selection passes, consolidate
the original repair and both follow-ups in one source checkpoint, retaining actual
results rather than predicted counts. Then obtain one connected Start/multiple-
frames/Stop/restart observation before unified-workspace integration. Preserve
workspace ownership through teardown, Stop all/deferred close, detector minima and
the strict flat profile. No unrelated audits or speculative hardware changes.
