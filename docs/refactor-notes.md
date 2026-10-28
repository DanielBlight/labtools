# Project cleanup and migration notes

> Historical checkpoint record. Some status and installer references below are superseded.
> Use [current architecture](architecture.md), [handover](ai-handover.md) and
> [roadmap](refactor-roadmap.md) for implemented status and the next task.


> Historical batch/backlog note. Current implementation status and task order are
> authoritative in [architecture](architecture.md), [roadmap](refactor-roadmap.md)
> and [handover](ai-handover.md). Technical details below are retained for context.

## Implemented

- Canonical `labtools gui TOOL` and `labtools simulate intensity-map` commands,
  with lazy launch routing and `python -m labtools` support.
- Existing launch commands and selected moved-module imports retained as shims.
- Map configuration extracted into `config/intensity_map.py`; acquisition
  re-exports the same class and schema version for existing callers.
- Backend selection moved from `simulation/map_backend.py` into
  `runtime/map_devices.py`; synthetic devices moved into `simulation/map_devices.py`.
- Lazy laser factory separated into `runtime/lazy_devices.py`.
- Narrow map-device protocols added for future session/simulation integration.
- Qt-free background processing moved into `processing/background.py`.
- Recipe Qt controls moved from `config/recipe_ui.py` into `gui/recipe_controls.py`.
- Known hardware test modules excluded before import without explicit opt-in.
- README reorganised; detailed hardware reference preserved in docs/hardware/;
  architecture, commands, development and simulation documentation reconciled.
- Regression tests added for dispatch, import isolation, compatibility, background
  processing, resource cleanup with fake devices and test collection guards.

## Intentionally unchanged

Real instrument wrappers; hardware command ordering and cleanup; voltage limits;
QSettings keys; output schemas; checkpoint version/signatures; synthetic scene
model, seed derivation and failure injection; native dependency constraints.
No physical hardware validation has been performed by this refactor.

## Compatibility

The old `operator_cli`, `gui.background`, `config.recipe_ui` and
`simulation.map_backend` modules remain as small public compatibility exports.
Use the new module locations for new code. Internal/private helpers and
monkeypatching globals through compatibility modules are not guaranteed APIs.
The old main.py still launches the spectrum GUI. No old launch command is removed.

## Scope boundary

This is a project-wide structural/documentation cleanup, not a rewrite of every
module. Large GUI classes and device wrappers remain in place to avoid mixing
untested signal/threading changes into cleanup. Shared connections, reservations,
a main GUI window, persistent HORIBA workers and expanded instrument simulation
are future steps, not delivered features. Existing separate tools must not be
used concurrently to control the same physical instrument.

## Applying and reverting

The supplied standalone installer checks the uploaded baseline, requires clean
tracked Git files for apply, backs up changed files, and refuses overwrites on
mismatch. It does not install packages, run hardware or commit changes.
Run --check before --apply. The installer prints the backup directory; use its
--rollback option with that exact directory before making subsequent edits.
Rollback refuses to overwrite files that differ from the installed payload.
Review the supplied patch and your Git diff before committing.

The historical install_intensity_map_simulation.py is retained for traceability,
not rerun or automatically deleted. It is not the installer for this cleanup.
