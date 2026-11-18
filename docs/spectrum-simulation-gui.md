# Synthetic spectroscopy in the existing operator GUI

This completes the bridge from the successful command-line spectrum rehearsal to the
existing spectrum operator window. It adds no simulator, hardware wrapper or new GUI.

## Launch

```powershell
uv run --no-sync labtools simulate spectrum --gui
```

Optional output override:

```powershell
uv run --no-sync labtools simulate spectrum --gui --output "C:\Labtools Simulation\Spectra"
```

This route always constructs the existing window with backend=simulation and
configuration_id=toy-scene-v1. No real detector options are imported. The preset token
syncerity is retained for schema compatibility, but gain/speed descriptions explicitly
say Toy/no detector; these are not physical configuration approvals. Default range is
500-600 nm and exposure is 0.065 s, matching the successful synthetic recipe rehearsal.

A permanent SIMULATION banner/window title identifies the mode. Optional laser controls
are disabled, and direct laser-action methods also return before hardware access.
Normal real-GUI defaults, laser behaviour and physical limits are unchanged.

## One operator pass

1. Confirm SIMULATION and no-laser indication. Leave the supplied toy range/settings.
2. Choose an output folder; tick Save CSV and Save PNG. Acquire a raw spectrum.
3. Capture reusable dark and save the offered NPZ. Enable dark subtraction and choose
   Use pre-taken stitched dark. Acquire again; inspect the lower corrected curve.
4. Acquire once more. Confirm repeated values and distinct output filenames.
5. Load the saved dark NPZ using the existing control. Changing exposure/range should
   mark it stale; do not bypass that validation.
6. Inspect the output folder: synthetic_*.npz, synthetic_*.csv and synthetic_*.png.
   CSV starts with a synthetic marker; NPZ carries backend/settings/dark provenance.
   Plot titles say SYNTHETIC and intensity units are arbitrary toy units, not counts.

The existing toy backend runs quickly. Stop may arrive after acquisition completes;
this is not a physical timing or mid-exposure cancellation test. The existing worker
cancellation contracts and command-line rehearsal evidence are unchanged.

The window does not gain new persistence or resume behaviour in this batch. The
headless rehearsal remains available for the full dark/archive/cancellation checks.
Do not use the normal `labtools gui spectrum` command for offline rehearsal.

## Focused validation

```powershell
uv run --no-sync ruff check --fix src/labtools/cli.py src/labtools/simulation/spectrum.py src/labtools/gui/spectrum_gui_horiba.py tests/test_spectrum_simulation_launcher.py tests/test_spectrum_gui_phase1.py
uv run --no-sync pytest -q -ra tests/test_spectrum_simulation_launcher.py tests/test_spectrum_gui_phase1.py
```

Eight launcher/action/plot/export tests passed in the sandbox. One actual offscreen
Qt workflow test skipped because PyQt6 is absent; this is not GUI acceptance. That test
uses the existing service, captures a dark, subtracts/repeats and checks exports while
forbidding native imports. Existing phase-1 GUI save expectations are updated for the
synthetic filename prefix. Local Qt execution and visual rehearsal remain required.
Ruff is unavailable in the sandbox. No full-suite rerun or hardware execution occurred.

Previous source linkage is preserved: 801-test evidence at 235f70ca..., wheel/staging
at 6074fdad..., startup-policy validation user-confirmed at 607c7db.... The confirmed
command-line spectrum rehearsal and its archives remain separate from GUI acceptance.
