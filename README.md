# labtools

Python tools for laboratory instrument control, acquisition, processing and
experimental diagnostics. Workflows include HORIBA spectra, scanning-mirror
intensity maps, laser annealing and an explicitly synthetic intensity-map backend.

Maintainers and coding models: start with [the repository handover](docs/ai-handover.md).
A headless synthetic spectrum-service example is also available. The ordinary spectrum
GUI now uses the service and requires a maintainer-supplied configuration identifier.

## Setup

Use Python 3.12 or newer and the project's existing uv environment:

```powershell
uv sync --dev
uv run labtools --help
```

Dependency requirements and vendor-driver requirements are unchanged by the
cleanup. `uv sync` refreshes installed console entry points; review any resulting
`uv.lock` changes. Do not remove native drivers or DLL configuration.

## Start a tool

```powershell
uv run labtools gui spectrum
uv run labtools gui mirror
uv run labtools gui intensity-map
uv run labtools gui anneal
```

These are **standalone tools**, not a shared-connection application. Existing
GUI connection behaviour is retained. Do not let separate tools control the
same hardware concurrently. Starting a GUI can initialize hardware according
to that tool's existing behaviour; GUI launch is not an offline test.

## Work offline

```powershell
uv run labtools simulate intensity-map --points 5
uv run labtools simulate intensity-map --gui
uv run python -m pytest -q
```

Only the intensity-map mirror, gate and counter have synthetic implementations.
There is no camera, annealing, spectrometer, shutter, rotation-stage or laser
simulation. Synthetic data is not calibration or a physical measurement.
The normal intensity-map GUI defaults to real mode; use the explicit simulation
command above for an offline GUI. Tests exclude the known hardware modules
before import unless `--run-hardware` is explicitly supplied.

## Operator workspace

```powershell
uv run labtools init "C:/Users/OPERATOR/Documents/Labtools Experiments"
uv run labtools doctor
```

`init` creates editable recipe files. `doctor` checks profile configuration, not
hardware connectivity or calibration. A maintainer-reviewed instrument profile
is required for the existing annealing workflow. See the operator guide.

## Documentation

- [Documentation index](docs/README.md)
- [Commands and compatibility](docs/commands.md)
- [Operator workspace and profile policy](docs/operator-workspace.md)
- [Intensity-map simulation](docs/intensity-map-simulation.md)
- [Spectroscopy, shutter, dark-frame and laser reference](docs/hardware/spectroscopy.md)
- [Architecture and future shared-session boundaries](docs/architecture.md)
- [Development and testing](docs/development.md)
- [Cleanup scope and migration notes](docs/refactor-notes.md)

## Safety and compatibility

Software checks do not replace physical interlocks, reviewed optical paths,
detector protection or instrument calibration. Keep the documented shutter,
SPAD-gate and laser procedures in place. A profile's approval flag is not
independent evidence of safety. Do not use example limits as a calibration.

The cleanup retains voltage limits, hardware command ordering, device wrappers,
QSettings keys, output formats, checkpoint schema and the synthetic scene model.
Legacy launch commands and selected moved-module imports remain available;
see the command guide. The large GUI classes have not been rewritten.

