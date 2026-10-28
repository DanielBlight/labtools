# Shared mirror/map backend: opt-in integration boundary

> Historical checkpoint record. Some status and installer references below are superseded.
> Use [current architecture](architecture.md), [handover](ai-handover.md) and
> [roadmap](refactor-roadmap.md) for implemented status and the next task.


> Historical batch/backlog note. Current implementation status and task order are
> authoritative in [architecture](architecture.md), [roadmap](refactor-roadmap.md)
> and [handover](ai-handover.md). Technical details below are retained for context.

## Scope

This batch extends the committed session foundation at 385df0d. It adds a narrow
LabJack mirror/gate service, an injected map-device provider, restricted cleanup
calls after faults, and fake-device tests. Existing standalone GUIs and their
launch commands are unchanged. No main window, shared synthetic scene, HORIBA
worker or alignment integration is introduced yet. Nothing is merged into main.

## Session cleanup policy

Normal calls still fault a resource on error and block further normal use and
new reservations until the session is closed/recreated. An active reservation
can call cleanup(resource, method) only for an argument-free method explicitly
allowlisted at session creation. The LabJack builder allows home and close_gate.
This does not reset the fault, reconnect a missing device, release the lease,
or certify physical safety. Other methods, lifecycle calls and arbitrary
arguments are rejected. Queued normal commands are checked again on the worker;
queued cleanup is still attempted after a prior command faults.

Cleanup on an unopened resource reports an error without opening it or creating
a new fault. If the factory already failed, its existing fault remains. Factories
must clean up their own partially constructed native resources. A constructor
that opens hardware and raises before returning remains the factory's concern.

Home is movement to the existing zero-voltage target, not a universal safe state.
The acquisition's existing checkpoint -> home -> gate-close order is retained.
If home fails, gate-close is attempted independently on the same worker before
the reservation is released. A gate-close failure is reported, not treated as
proof that the gate closed. This is not a hardware interlock or emergency stop.

## LabJack service

LabJackWiring defaults to mirror DIO 2/3 and gate 0. The new opt-in service checks
integer pins in the supported 0..15 range and rejects gate/mirror overlap. It
validates movement using the existing -10..+10 V manual-mirror bounds; mapping
continues to validate its configured limits before calling the service.

Construction, movement, gate operations and disconnect run on one persistent
session worker. No raw native handles are returned by the public service.
Creating a session does not connect. Releasing a measurement does not disconnect.
Service shutdown attempts gate-close and device-close independently, without
homing. That extra gate-close on session shutdown is specific to this new path;
legacy manual disconnect behavior is not changed.

## Acquisition injection

acquire_intensity_map now accepts the optional keyword device_provider. With no
provider, the existing real/simulation open_map_devices path is unchanged.
SharedMapProvider(session, ...) is a context provider that reserves the physical
LabJack for the whole measurement and cleanup. It rejects backend/wiring mismatch
before device creation. The IDQ connection remains per-map, on the acquisition
thread; its integration does not block the LabJack worker, but the LabJack lease
still prevents conflicting manual movement throughout that integration.

A caller can supply an explicit synthetic/fake counter provider with
backend='simulation'. This is an injection boundary, not a production shared
simulation implementation. The regression tests use explicitly injected fake
mirror/gate/counter objects and temporary synthetic-labelled output. They are
not measured data or a validated physical model. Existing scene simulation and
its checkpoint signatures remain unchanged.

The application must own the session and close it only after jobs finish cleanup
and release reservations. SessionMirror and SessionGate are short-lived adapters
bound to one lease; they are invalid after it is released. A manual controller
will use the same session with its own reservation in the next GUI integration.
Do not wire these into two independent processes and expect cross-process locking.

## What the tests cover

- Manual -> map -> manual reuse of one fake LabJack connection.
- Mirror/gate alias conflicts, full-map and in-flight cleanup ownership.
- Cancellation/resume without reconnecting and matching backend/wiring checks.
- Mirror, gate, counter, checkpoint, construction and shutdown failure paths.
- Original failure preservation, independent gate-close attempts after home fails.
- Faulted normal-command rejection, queued cleanup, stale lease and allowlist guards.
- Native-import isolation and unchanged legacy default acquisition tests.

Offline tests do not validate Windows drivers, physical wiring, voltage calibration,
SPAD gate timing, Qt rendering or instrument safety. Native calls have no new
abort mechanism or deadline; a blocked driver can still delay cleanup/shutdown.
IDQ ownership against other standalone tools is not coordinated by this batch.

## Apply and test

Keep feature/shared-instrument-session checked out and close running GUIs.
The supplied apply_labtools_shared_backend.py checks the affected baseline,
requires clean tracked Git files and refuses main/master/detached HEAD. It backs
up exact original bytes and prints a guarded rollback command. It does not run
hardware, install packages, change branches, stage files or commit anything.
Trailing newline differences and UTF-8 BOM/CRLF are accepted for baseline checks.

Run separately:

    python .\apply_labtools_shared_backend.py --check
    python .\apply_labtools_shared_backend.py --apply
    uv run --no-sync python -m pytest --disable-plugin-autoload tests/test_shared_map_backend.py tests/test_session_cleanup.py tests/test_session_core.py -q
    uv run --no-sync python -m pytest --disable-plugin-autoload -q

Use the same external Python environment/copy-mode settings as your working
refactor session. Review git diff and git status before committing. Do not apply
the optional review patch as well as the installer. Keep backups outside commits.

## Next boundary

One application will inject this provider into mapping and the same session into
manual mirror control. It must display reservation/fault state and prevent unsafe
shutdown while jobs are active. Alignment remains planned for a separate persistent
HORIBA asyncio worker, not this synchronous LabJack service. Preserve its tested
standalone version on main until that integration is verified on the feature branch.
