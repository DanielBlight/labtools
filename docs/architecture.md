# Architecture

## Current responsibilities

- `cli.py`: argument parsing and command dispatch. Help and validation avoid Qt
  and native hardware imports.
- `launchers.py`: lazy registry of standalone GUI entry points. It does not own
  a QApplication, cache connections or instantiate shared windows.
- `config/`: recipes, instrument profiles and intensity-map configuration.
  `config/recipe_ui.py` is a compatibility shim; actual Qt controls are in `gui/`.
- `gui/`: widgets, Qt workers and recipe controls. Large existing window classes
  remain in place; their QSettings names and device sequencing are unchanged.
- `acquisition/`: measurement loops, cancellation, checkpointing and output.
- `runtime/`: backend selection and per-acquisition resource lifecycle. The
  existing map factory lives here, separate from synthetic device models.
- `devices/`: real instrument wrappers. No wrapper has been renamed or rewritten.
- `simulation/`: synthetic map devices, deterministic scene and runner.
- `processing/`: Qt-free background CSV parsing and subtraction.
- `visualisation/`: existing intensity-map colour mapping and plotting helpers.
- `io/`: retained namespace; output logic has not all been moved into it.

## Map boundary

`IntensityMapConfig` lives in `config/intensity_map.py` and remains importable
from `acquisition/intensity_map.py`. Its fields, validation and checkpoint
signature are unchanged. The schema version remains 1.

`runtime.map_devices.open_map_devices` yields `(mirror, gate, counter)`.
`runtime.contracts` describes the narrow methods used by acquisition. These
are structural typing contracts, not a new inheritance requirement or a
runtime safety validator. Real wrappers and synthetic devices remain distinct.

Real selection lazily imports the existing wrappers and uses the original
ExitStack ordering. Synthetic selection creates one shared synthetic state and
closes it at context exit. There is no fallback from a real failure to synthetic
operation. The scene's model version and coordinate/channel seeding are unchanged.

The acquisition loop still owns its existing home/gate cleanup. The factory
has not acquired new interlock or safe-state guarantees. Review the existing
cleanup paths separately before changing their behaviour.

## Later shared application: design constraints, not implemented functionality

A future application/session layer should own one connection per physical
instrument and pass services into tool windows. It should not make windows
reach into each other's controls or instantiate drivers independently.

Reservations must cover whole measurements, not only individual commands.
Manual mirror controls may stay visible while mapping owns movement, but
conflicting writes should be blocked. LabJack reservations must account for
both mirror and gate users, not treat those as independent physical devices.

Closing a tool window should release its reservation without disconnecting
other users. Application shutdown must stop jobs, perform reviewed cleanup,
and close resources in their owning thread/event loop. A mutex alone does not
make a native driver thread-safe.

HORIBA connections are tied to their asyncio loop. Keep connect/use/disconnect
on one persistent worker loop before introducing reuse. The existing
AsyncTaskRunner still uses a fresh loop per operation and is not a persistent
connection worker. Do not cache a HORIBA object across those loops.

## Later simulation expansion

Select real or synthetic explicitly at the session boundary. Extend contracts
only when a workflow needs them; do not create a single universal fake device.
Synthetic devices should exercise acquisition logic, cancellation and cleanup
without importing native wrappers. Keep model provenance and backend-specific
checkpoint validation. A future shared synthetic session will need intentional
state ownership; the current factory creates fresh state per acquisition.
