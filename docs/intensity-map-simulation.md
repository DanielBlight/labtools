# Offline intensity-map simulation, v1

Install on `feature/hardware-simulation`, from a clean committed checkout.
The self-contained installer updates the acquisition and GUI modules in place
using AST-located edits. It adds a simulation package, tests and this guide.
It does not replace the entire GUI or device wrappers.

## Install

    uv run python install_intensity_map_simulation.py --check
    uv run python install_intensity_map_simulation.py
    uv run python -m pytest --noconftest tests/test_intensity_map_simulation.py -q

`--noconftest` isolates this test file from existing hardware fixtures and
collection-time native imports in the repository's conftest files. The tests
provide their own fixtures. Do not add `--run-hardware` to this command.

No additional dependencies are required beyond the project's existing NumPy,
Matplotlib, pytest and (for the GUI) PyQt6. The installer itself uses only the
standard library. It does not run pip, uv sync, or connect devices.

## Launch

    uv run python -m labtools.simulation.intensity_map --gui

This starts the existing intensity-map GUI with simulation selected. It shows
a SIMULATION banner and disables real laser actions. The normal GUI launcher
still defaults to real mode; select the explicit Simulation checkbox to use
synthetic devices. Backend selection is not persisted and cannot change while
a map or laser session is active. Close/reopen the GUI to release a connected
real laser before switching to simulation.

A headless two-channel synthetic map:

    uv run python -m labtools.simulation.intensity_map --points 15

A stopped map:

    uv run python -m labtools.simulation.intensity_map --points 15 --stop-after 40

Resume using the printed dataset directory:

    uv run python -m labtools.simulation.intensity_map --resume "FULL DATASET PATH"

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

The development validation used a representative acquisition fixture rebuilt
from the retrieved source interfaces, not a byte-for-byte local copy of the
current repository. Full Qt/hardware execution was unavailable.

## Rollback

    uv run python install_intensity_map_simulation.py --rollback

Backups are in .labtools-migrations/intensity-map-simulation-v1. Do not commit
that directory. Rollback refuses to overwrite files modified after installation,
including formatting changes. Review the diff and keep the backup until tested.
