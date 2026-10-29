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

## Source-tree fallback and alignment

If console entry points are absent in an existing unsynced environment, use the
current source tree explicitly rather than guessing a missing executable:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
uv run --no-sync python -m labtools --help
uv run --no-sync python -m labtools.simulation.intensity_map --gui
```

Alignment has a module entry point, not a registered `labtools gui alignment` command.
Its ordinary module launch is real hardware and requires a reviewed configuration ID;
see [alignment](horiba-alignment.md). Shared manual/map composition remains a Python
injection API, not a permanent launcher. Separate standalone tools do not coordinate.
Remove QT_QPA_PLATFORM=offscreen before interactive GUI checks.

## Alignment lifecycle acceptance

The exact focused test and validation commands are in the
[lifecycle acceptance guide](alignment-lifecycle-acceptance.md). These tests use fake
backends and do not require --run-hardware. No shared launcher command is introduced.

## Protected lab-PC installation and updates

The [deployment guide](lab-pc-deployment.md) provides proposed Windows packaging,
offline installation, operator launch, permissions, updates and rollback commands.
Development uv commands are not operator startup/update commands. Use the accepted
release's full interpreter path and a non-editable installed wheel. No automatic
updater or new shared-launcher command is introduced. The [Qt gate](qt-gate-status.md)
remains open; do not deploy this branch as accepted production based on skipped tests.

## Current audit checkpoint and gate evidence

See [wrapper audit checkpoint](wrapper-audit-checkpoint.md) for the current docs-only
installer and exact commands. Capture full local Qt output plus JUnit XML; a pass count
copied from documentation is not evidence that QtWidgets ran. Do not run hardware tests
or diagnostic scripts as an installation check. The collision fix remains gated.

## ITC W1 lifecycle contract

See [current checkpoint](itc4000-lifecycle-checkpoint.md). Ordinary transport cleanup
failures now raise ExceptionGroup; callers catching Exception still receive them.
Interrupt/cancellation remains primary. Startup/body errors retain cleanup notes and
structured _itc4000_cleanup_failures. Teardown blocks commands permanently; explicit
close retries only failed handles, with no guarantee a manager-invalidated handle can
recover. No physical output commands are added. Do not auto-reconnect or silently retry
commands. Whole-module fake-PyVISA tests supplement historical AST/adapter probes.

## HORIBA W2 lifecycle contract

See [W2 checkpoint](horiba-lifecycle-checkpoint.md). Real wrapper startup/teardown now
retains primary/cancellation and independently attempts CCD, mono and manager cleanup.
Failed handles are uncertain and only explicit disconnect retries them; reconnect and
commands after teardown are refused by cleared public handles/teardown state. Do not
add timeout/exposure/persistent-connection changes to this checkpoint. Whole-module
fake SDK tests supplement adapter fakes; neither establishes physical SDK/shutter safety.
## W5 scanning-mirror preflight status

W5 is implemented/offline-tested at input HEAD `d2e29eb929567cdcc10bdf3fff907044c6815369`.
Both finite requests and representable calibrated codes are checked before either write;
A/B protocol and calibration maths remain unchanged. Channel-B ordinary failure now
reports uncertain partial movement with no rollback/home. Validation: 11 dedicated,
89 focused, full 404 passed / 5 skipped. PyQt6 is absent, so Qt remains gated. See
[W5 checkpoint](scanning-mirror-preflight-checkpoint.md). IDQ P0 remains open.
## UC480 lifecycle status

UC480 partial setup/start cleanup is implemented/offline-tested at HEAD `b4be98c4f619526a421af54f795365f14d95ac54`. Validation: 16 dedicated; 27 camera+regression; full 420 passed / 5 skipped. PyQt6 absent, so Qt remains gated. See [UC480 checkpoint](uc480-lifecycle-checkpoint.md). IDQ P0 remains open.

## SC10 checkpoint status

SC10 serial startup/teardown and fake transcript coverage are implemented at HEAD `f054ad5`. Full-suite validation must be rerun locally because the execution wrapper interrupted the combined run. See [SC10 checkpoint](sc10-lifecycle-checkpoint.md). IDQ P0 and Qt remain open.

## Scriptable measurement API requirement

The final product must provide a stable Qt-free `labtools.measurements` facade over shared services/acquisition logic, with validated immutable requests/results, explicit backend/profile provenance, session reservations, deterministic cleanup, progress/cancellation and GUI/script parity. Spectrum and intensity map delegate to existing services; hyperspectral must be rebuilt from the legacy runner before export. See [scriptable measurements](scripted-measurements.md).

Kinesis finite native-unit validation and close ownership are implemented at HEAD `bea41a66`; 15 dedicated fake-SDK tests passed. Full-suite rerun remains local because the execution wrapper interrupted it. See [Kinesis checkpoint](kinesis-lifecycle-checkpoint.md).

## Scripted spectrum facade

The Qt-free spectrum facade is implemented; see [checkpoint](measurements-spectrum-checkpoint.md) and [usage](scripted-measurements.md). Map, hyperspectral and anneal facades remain planned.

## Scripted dark records

Qt-free dark capture, immutable reuse and NPZ helpers are implemented; see [checkpoint](measurements-dark-checkpoint.md).

## Scripted alignment frames

Qt-free sync/async alignment acquisition is implemented; see [checkpoint](measurements-alignment-checkpoint.md).

## Scripted intensity maps

The Qt-free resumable intensity-map facade is implemented; see [checkpoint](measurements-intensity-map-checkpoint.md). Map algorithms, schema and persistence are unchanged.

## Unified measurement runtime

A Qt-free `MeasurementRuntime` now composes the existing spectrum and map runtimes without changing their ownership models; see [checkpoint](measurements-runtime-checkpoint.md).
