# Next recommendations: cleanup and GUI boundaries

> Historical checkpoint record. Some status and installer references below are superseded.
> Use [current architecture](architecture.md), [handover](ai-handover.md) and
> [roadmap](refactor-roadmap.md) for implemented status and the next task.


> Historical batch/backlog note. Current implementation status and task order are
> authoritative in [architecture](architecture.md), [roadmap](refactor-roadmap.md)
> and [handover](ai-handover.md). Technical details below are retained for context.

## Changes

- Map cleanup attempts checkpoint, mirror home, and gate close independently, in
  the existing order. Setup/channel-configuration/gate-opening failures are now
  inside this cleanup scope too. This explicitly changes failure-path behavior:
  homing and gate closure are attempted after setup failure.
- An acquisition exception remains the primary exception. Secondary cleanup and
  checkpoint-retry failures are attached as exception notes. Without a primary
  failure, cleanup failures are reported as an ExceptionGroup. A failed checkpoint
  is never reported as definitely saved.
- MapController owns the worker and QThread until the thread has finished. It
  rejects overlapping starts and exposes progress, finished, failed, and idle.
  Cancellation uses a thread-safe Event, not a queued slot blocked behind run().
- MapWorker and HardwareThread remain importable from their previous GUI modules.
- Manual mirror hardware creation is injectable. The default factory imports
  native drivers only when connecting, and closes a partially constructed
  connection if mirror construction fails. No shared connection manager is added.
- The spectroscopy guide now describes the existing mean/std single-pass clipping
  algorithm, rather than claiming a median/MAD algorithm. Processing is unchanged.

## Preserved behavior

Settings keys, output/checkpoint formats, simulation labeling, default real-device
selection, manual mirror voltage limits/DIO pin, and successful acquisition
sequencing are unchanged. Manual connect/disconnect/exit still sends no home or
move command. Stop remains cooperative and cannot interrupt a blocked native call.
This change is not a hardware safety interlock or a guarantee of successful cleanup.

## Validation

Run from the repository root:

```powershell
uv run pytest -q
uv run pytest tests/test_cleanup_failures.py tests/test_qt_controllers.py -q
uv run pytest tests/test_gui_lifecycle.py -q
```

The Qt tests use fake devices and injected acquisition functions, not hardware.
Window tests run in subprocesses with isolated settings. They require usable
PyQt6 QtWidgets libraries. If unavailable, pytest reports a skipped module.
The implementation environment ran the QtCore controller tests but could not
load QtWidgets because libEGL.so.1 was missing. No physical hardware was tested.

## Install

Use the separate apply_labtools_next.py installer from the repository root.
It defaults to a dry run, checks every affected file against the supplied source
snapshot, and refuses unexpected edits before changing anything. --apply writes
backups under .labtools-refactor-backups and prints the rollback command. --rollback
restores exact original bytes and refuses files edited after installation.

The accompanying patch is for review or manual application, not required by the
installer. Close running GUIs before applying. Commit or otherwise back up local
work first. A larger rewrite of laser control, a shared device manager, and native
call timeouts are deliberately outside this batch.
