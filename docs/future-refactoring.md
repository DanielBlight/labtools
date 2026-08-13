# Future refactoring notes

Backlog of structural/maintainability ideas identified during the August 2026
refactor pass. None of these are broken today — they're maintenance and
scaling concerns to revisit as the project grows, not urgent fixes.

## 1. Separate runnable experiment scripts from library code

`src/labtools/acquisition/run_hyperspectral_scan.py` lives inside the
`labtools.acquisition` package alongside genuine reusable library code
(`range_spectrum.py`), but it's really a one-off experiment runner:

- It executes side effects at **module import time**, not just when run as a
  script: `matplotlib.use('Qt5Agg')` and `os.makedirs(OUTPUT_FOLDER, ...)`
  happen unconditionally on `import`, outside the `if __name__ == "__main__":`
  guard. Anything that imports this module for any reason (e.g. to reuse a
  constant) will silently create a directory and switch the global matplotlib
  backend.
- It hardcodes a personal path (`C:\Users\Legend\...`) and one-off experiment
  constants (wavelength range, mirror voltages, laser current, band
  definitions) as module-level globals.
- Its only import of `xarray` is why that dependency was undeclared in
  `pyproject.toml` — it's used by a script, not the core package.

**Suggested fix (later):**
- Move genuinely one-off experiment scripts to a top-level `scripts/` folder
  outside `src/labtools/`, so the installable package stays side-effect-free
  to import.
- Or, at minimum, wrap all module-level side effects (matplotlib backend
  setup, directory creation) inside `main()`/`run()` so importing the module
  never has side effects.
- Centralize hardware addresses/paths/experiment constants (see item 4) so
  scripts don't hardcode a specific user's filesystem layout.

## 2. `spectrum_gui_horiba.py` is still a large single `QMainWindow`

After extracting `AsyncTaskRunner` and the background-math helpers, the
window class (`src/labtools/gui/spectrum_gui_horiba.py`) still owns:
spectrometer connect, laser connect, VISA test, acquisition orchestration,
and save-to-disk, all in one ~570-line class.

**Suggested fix (later):** split into composed panel widgets, e.g. a
`SpectrometerPanel` and a `LaserPanel`, each a `QWidget` embedding its own
controls/signals, composed into the main window. Makes each concern
independently testable and easier to navigate.

## 3. No automated tests beyond the IDQ time controller

`horiba_spectrometer.py`'s frame-combination logic (median/sigma-clip),
`range_spectrum.py`'s dark-frame timing logic, and `gui/background.py`'s
parsing/subtraction are pure-ish logic that could be unit tested with
fakes/mocks for the hardware-dependent bits — no real hardware required.
Currently a regression there would only surface by hand-testing through the
GUI.

**Suggested fix (later):** add unit tests for:
- `HoribaSpectrometer.get_spectrum()`'s median/sigma_clip math (mock
  `_acquire_single`)
- `range_spectrum.py`'s dark-frame timing resolution (`"single"` vs
  `"per_frame"`)
- `gui/background.py`'s `parse_background_csv` / `apply_background_subtraction`
  (already Qt-free, easiest to start with)

## 4. Scattered hardware addresses/config across files

VISA address, Time Controller IP, output paths, laser current, etc. are
hardcoded independently across `itc4000.py`, `run_hyperspectral_scan.py`,
`tests/conftest.py`, and GUI defaults.

**Suggested fix (later):** a single config file (TOML or environment
variables) so changing hardware/IP/paths is a one-line edit instead of a
grep-and-replace across files.

## 5. Minor: `HoribaSpectrometer.PRESETS` is a mutable class-level dict

Flagged by the linter as a mutable default at class scope. Low risk today
since it's only read from, but worth switching to `types.MappingProxyType`
or moving into `__init__` if you want to eliminate the warning and guard
against accidental mutation.

## Known pre-existing gaps (flagged, not fixed)

- `xarray` is imported by `run_hyperspectral_scan.py` but not declared in
  `pyproject.toml` dependencies.
- `README.md` is currently empty — worth a short project overview, `uv`
  setup instructions, and how to launch the GUI.
