# Session foundation (opt-in, not GUI integration)

> Historical checkpoint record. Some status and installer references below are superseded.
> Use [current architecture](architecture.md), [handover](ai-handover.md) and
> [roadmap](refactor-roadmap.md) for implemented status and the next task.


> Historical batch/backlog note. Current implementation status and task order are
> authoritative in [architecture](architecture.md), [roadmap](refactor-roadmap.md)
> and [handover](ai-handover.md). Technical details below are retained for context.

Adds runtime/session.py and offline fake-device tests. Existing GUI, acquisition,
wrappers, limits, output and checkpoint files are untouched.

InstrumentSession accepts explicit physical-resource factories and direct aliases.
Reserve mirror and gate against the same labjack key. Reservations are atomic,
exclusive and non-reentrant, even for identical owner labels. Hold a reservation
through the complete measurement and its cleanup. Release does not disconnect.
Factories, public service calls and close run on one persistent worker thread.
Connections are lazy and reused until explicit session shutdown. A command or
factory failure faults that physical resource and blocks further calls/reuse.
Shutdown refuses active leases, attempts every connected resource close, and
reports failures. Context managers preserve primary errors with cleanup notes.

No hardware factories are supplied. Factories must return a service with close()
and clean up partially constructed resources themselves. Use reviewed narrow
service methods, not raw device handles; do not return native objects to callers.
Do not recursively invoke or close a session from its worker.

Limits: process-local coordination only, no cross-process exclusion, interlocks,
forced cancellation, blocked-driver deadlines, or automatic safe-state actions.
The existing standalone tools do not participate and remain unsafe to run
concurrently against the same hardware. HORIBA loop ownership is not addressed.

Next integration: a reviewed LabJack mirror/gate service, injected acquisition
boundary, and one application owning both windows. Do not wire existing raw
wrappers into this foundation and assume safety. Measurement-specific gate/home
cleanup must run before releasing its reservation. Cancellation must finish
cleanup before release; a caller interruption does not stop a native operation.

Validation:
    uv run --no-sync python -m pytest tests/test_session_core.py -q
    uv run --no-sync python -m pytest -q

This batch has no new main window and no change to launch commands.
