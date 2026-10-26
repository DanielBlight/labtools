# Commands and compatibility

Run these from the project folder after `uv sync --dev`. The `labtools` console
script and `python -m labtools` call the same command-line implementation.

## Standalone GUIs

```powershell
uv run labtools gui spectrum
uv run labtools gui mirror
uv run labtools gui intensity-map
uv run labtools gui anneal
```

The tool names describe the workflow; hardware-specific Python module names
remain unchanged for compatibility. These commands do not implement a shared
GUI or shared instrument ownership. Existing per-tool hardware initialization
and profile requirements remain in effect.

## Explicit simulation

```powershell
uv run labtools simulate intensity-map --help
uv run labtools simulate intensity-map --points 15 --seed 0
uv run labtools simulate intensity-map --gui
uv run labtools simulate intensity-map --points 15 --stop-after 40
uv run labtools simulate intensity-map --resume "PATH/TO/SIMULATION/RUN"
```

Simulation options are forwarded to the existing runner. Its defaults, seed
semantics, GUI controls, checkpoint behaviour and output marking are unchanged.
The runner refuses to resume real-hardware data. The synthetic runner's GUI
continues to use its existing controls; not every headless flag is applied to
the GUI. Consult `--help` and the simulation guide.

## Workspace and annealing

```powershell
uv run labtools init "C:/Users/OPERATOR/Documents/Labtools Experiments"
uv run labtools doctor
uv run labtools validate "PATH/TO/recipes/anneal.json"
```

These three commands do not open devices. `doctor` validates the instrument
profile only. Actual command-line annealing remains:

```powershell
uv run labtools anneal "PATH/TO/recipes/anneal.json" --confirm-optical-path
```

That last command executes hardware operations. The confirmation flag does not
perform physical checks; follow the operator guide before using it.

## Existing commands retained

- `uv run python main.py`: spectrum GUI, as before.
- `uv run labtools-anneal`: same as `labtools gui anneal`.
- `uv run labtools-intensity-map`: same as `labtools gui intensity-map`.
- `uv run python -m labtools.gui.spectrum_gui_horiba`: unchanged module entry point.
- `uv run python -m labtools.gui.mirror_voltage_gui`: unchanged module entry point.
- `uv run python -m labtools.gui.intensity_map_gui`: unchanged module entry point.
- `uv run python -m labtools.gui.laser_anneal_gui`: unchanged module entry point.
- `uv run python -m labtools.simulation.intensity_map`: existing synthetic runner.
- `uv run python -m labtools.operator_cli`: compatibility CLI entry point.

Additional short aliases are `labtools-spectrum`, `labtools-mirror` and
`labtools-simulate-map`. They do not provide different connection behaviour.
