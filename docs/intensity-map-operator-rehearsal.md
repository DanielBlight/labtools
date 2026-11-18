# Offline intensity-map operator rehearsal

Use the existing simulation entry point, not `labtools gui intensity-map`.
No device, laser, shutter or stage is simulated beyond the existing synthetic
map mirror/gate/counter backend. Synthetic results are not calibration data.

## Launch

From the repository root, in the existing development environment:

```powershell
uv run --no-sync labtools simulate intensity-map --gui --realtime --points 5 --seed 42
```

The window is simulation-only: its backend checkbox stays checked and disabled,
including after a map finishes. Laser controls remain disabled. A title/banner and
plot titles identify synthetic data. Normal real-hardware launch behaviour is unchanged.

`--realtime` makes integration/settling delays visible so Stop can be rehearsed.
Without it synthetic scans intentionally run as fast as possible. `--seed` now reaches
the GUI acquisition configuration. Seed/timing are launch options, not persisted
settings; resumed checkpoints retain their recorded simulation settings.

Simulation preferences use a separate `IntensityMapSimulation` settings store,
leaving the normal GUI's preferences untouched. Without explicit `--points` or
`--output`, the launcher respects the simulation window's remembered grid and output.
For subsequent sessions, omit `--points` to retain your last grid:

```powershell
uv run --no-sync labtools simulate intensity-map --gui --realtime --seed 42
```

Default simulation output is under your home directory's `Labtools Simulation`.
Use `--output "C:\path\to\simulation-data"` only to override it deliberately.
The backend adds a `SIMULATION` directory and a unique synthetic run directory.

## One practical rehearsal

1. Confirm the SIMULATION banner and disabled laser/backend controls.
2. Set a 5 by 5 grid, integration 0.02 seconds and settle 0. Leave final-output saving on.
3. Start a map. Confirm the displayed synthetic map, voltage axes, colourbar and 100%
   progress. Check the reported output folder.
4. Change to 20 by 20, start, then press Stop after progress appears. Wait for cleanup
   and controls to become available. The run should report a saved checkpoint.
5. Press Resume and select that incomplete run directory, not the parent directory.
   The recorded configuration is restored. Confirm completion in the same directory.
6. Start a new 5 by 5 map. Confirm a new output directory rather than overwritten data.
7. Change grid/output preferences, close, reopen without explicit overrides, and confirm
   they were retained. Normal hardware-mode settings should not be affected.

## Saved output

- `SYNTHETIC_DATA.txt`: unmistakable synthetic marker.
- `intensity_map_metadata.json`: configuration, seed, backend and completion state.
- `intensity_map_checkpoint.npz`: retained for incomplete maps and removed on completion.
- `intensity_map_points.csv`: per-point values and completion information.
- `channel_<n>_count_rate_matrix.csv`: channel matrix exports.
- `intensity_map_complete.npz`: arrays with synthetic/backend markers.
- `summed_intensity_map.png`: saved plot with synthetic title and colourbar.

The existing save option controls final data/plot exports. Metadata and incomplete-run
checkpoints are retained independently; disabling final exports does not mean no files.

## Recovery

Invalid settings/channels are reported before starting. Resume refuses a mismatched
real/simulation checkpoint. For an acquisition failure, inspect the existing error
Details and output folder; resume only a directory with a valid checkpoint. Do not
switch to real mode to recover a simulation run. CLI `--resume`/`--stop-after` are
headless operations; with `--gui`, use the window buttons instead of ignored flags.

## Implementation evidence and limits

The source review found: an offline launcher could switch to real mode, GUI seed/timing
flags were ignored, launcher defaults overwrote remembered settings, and simulation
preferences shared the normal settings store. This batch corrects those together.

A real headless synthetic CLI rehearsal completed 25 points, stopped at 7, resumed to
25, and repeated into a distinct directory. Resumed/repeated counts matched the first
run exactly. Marker, metadata, CSV, NPZ and PNG were checked. No hardware imports or
connections were required. Existing backend tests and launcher tests: 28 passed,
1 skipped, 172 plotting-library deprecation warnings in 32.28s in the review sandbox.
The skip is the entire Qt rehearsal module: PyQt6 is unavailable there. It is not GUI
acceptance. Two actual offscreen GUI tests are supplied for the development PC,
covering locked mode/preferences and complete-stop-resume-repeat acquisition.

Ruff is unavailable in the sandbox. Run focused lint/tests locally; do not repeat the
full acquisition suite merely to recover counts. The GUI must still be visually
rehearsed by the operator. No hardware, packaging, anneal, ID900 or runner changes.
