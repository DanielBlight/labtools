# Offline intensity-map simulation

Simulation is already part of the source tree. Run `uv sync --dev` to refresh
entry points. Do not rerun the historical `install_intensity_map_simulation.py`
against refactored files; it targets the older source layout.

Run offline tests with `uv run python -m pytest -q`. The known hardware modules
are now excluded before import by default; `--noconftest` is not required.

## Launch

    uv run labtools simulate intensity-map --gui

This starts the existing intensity-map GUI with simulation selected. It shows
a SIMULATION banner and disables real laser actions. The normal GUI launcher
still defaults to real mode; select the explicit Simulation checkbox to use
synthetic devices. Backend selection is not persisted and cannot change while
a map or laser session is active. Close/reopen the GUI to release a connected
real laser before switching to simulation.

A headless two-channel synthetic map:

    uv run labtools simulate intensity-map --points 15

A stopped map:

    uv run labtools simulate intensity-map --points 15 --stop-after 40

Resume using the printed dataset directory:

    uv run labtools simulate intensity-map --resume "FULL DATASET PATH"

The headless runner defaults to fast operation; `--realtime` honours integration
and settling delays. The GUI uses real-time delays so Stop can be exercised.
The headless --seed option applies to new headless maps; the GUI currently uses
seed 0 and has no seed editor. A resumed map restores its saved seed.

## Model and provenance

The mirror, SPAD gate and counter share a per-session state. Counts come from
a synthetic two-Gaussian scene plus background and Poisson counting noise.
The scene is scaled to the requested voltage range, not to physical distances.
Threshold and edge settings are recorded/validated but do not model detector
electronics. Integration time scales expected counts. Closed gate gives zero.
The per-coordinate/channel seed makes resumed counts match uninterrupted maps.
This is synthetic development data, not a model validated against your optics.

New synthetic datasets go under an additional SIMULATION subdirectory and have
SYNTHETIC_DATA.txt plus explicit JSON and final NPZ provenance. PNG titles and
live plot titles are marked SYNTHETIC. Existing CSV names/schema are retained:
keep them with the dataset metadata and marker, not as standalone measurements.
Real checkpoint signatures retain their legacy shape. Cross-backend resume is
rejected before device creation. A simulation never silently replaces a failed
real connection. Simulation seed/model changes invalidate simulation resume;
real-time delay and fault-injection changes do not.

Failure injection is available programmatically:

    config = dataclasses.replace(config, simulation_fail_after_points=4)

Clear this option before resuming. It counts measurements in the current session.

## Limits and validation

This first phase covers intensity mapping only. It does not simulate the camera,
annealing, shutter, rotation stage, spectrometer or laser power. Real laser
controls are disabled rather than simulated. Existing native-driver issues and
physical safety checks are not solved by simulation.

The package includes offline tests for one/two-channel maps, stop/resume,
fault checkpoints, seed reproducibility, provenance, backend isolation and GUI
laser-action guards. These do not prove Qt rendering, real-device behaviour,
physical timing, wiring or calibration. Run the tests on your actual checkout.

The cleanup was checked against the uploaded source snapshot with offline tests
and a headless synthetic map. Full Qt/Windows/hardware execution was unavailable.

## Reverting the cleanup

Use the cleanup installer's guarded rollback with the backup path it prints.
Do not run the historical simulation installer or its rollback against the new
layout. Keep older migration backups for traceability, not as a current update path.

## Current reliability gate and wrapper audit

No allocation, schema, resume or deterministic-model change is made by the
[wrapper-audit checkpoint](wrapper-audit-checkpoint.md). The same-second output-folder
collision remains planned pending executed QtWidgets acceptance. The independent
[wrapper plan](device-wrapper-repair-plan.md) does not certify real hardware from
synthetic success and must not change model/seeding/signatures during device repairs.
