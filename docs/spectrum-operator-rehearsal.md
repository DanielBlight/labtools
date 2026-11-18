# Offline spectroscopy rehearsal

This is the next complete development-PC workflow after intensity mapping: acquire a
synthetic spectrum, capture/save/reload a dark, subtract it, repeat, export and reopen
the results. It uses existing SpectrumRuntime, measurement facades and NPZ writers.
No production module, real GUI, backend, device wrapper or configuration is changed.

## Run

From the repository root in the existing environment:

```powershell
uv run --no-sync python examples/measurements/rehearse_spectrum.py --recipe examples/measurements/recipes/spectrum_simulation.json
```

The supplied toy recipe is explicitly synthetic. Its detector preset and numeric
settings are demonstration inputs, not approved physical operating settings.
Real recipes, other recipe kinds and pre-subtracted starting recipes are refused.

Default output is under your home directory in `Labtools Simulation/Spectra/SIMULATION`.
Each run creates a new timestamped folder; repeats never replace an earlier run.
To choose another output root:

```powershell
uv run --no-sync python examples/measurements/rehearse_spectrum.py --recipe examples/measurements/recipes/spectrum_simulation.json --output "C:\Labtools Simulation\Spectra"
```

## What to inspect

Open the reported folder and view `spectrum.png`. It overlays raw synthetic intensity,
the stored dark and the dark-subtracted result. The wavelength axis is in nm and the
toy intensity is in arbitrary units; the title explicitly says SYNTHETIC.

`spectrum.csv` contains wavelength, raw, dark and corrected columns. Its first line
labels synthetic data. NPZ metadata and rehearsal.json, not CSV alone, carry the full
settings/provenance. Do not use this CSV as a verified dark archive.

Files:
- SYNTHETIC_DATA.txt: synthetic marker.
- dark.npz: existing provenance-bearing dark archive.
- raw_spectrum.npz and corrected_spectrum.npz: existing pickle-free result format.
- spectrum.csv and spectrum.png: convenient inspection outputs.
- rehearsal.json: input recipe hash/settings, completed checks and status.

The script actually checks dark round-trip, subtraction, repeat equality, cancellation
before acquisition, reuse after cancellation, mismatched-dark rejection, and reopened
result metadata/arrays. Cancellation is not an interactive stop/timing test. It does
not simulate the physical shutter, detector, stitching, optical alignment or electronics.

Run again and confirm a different folder. The existing deterministic toy spectrum
should repeat exactly for unchanged settings. Edit only a copy of the example recipe
if you want to explore different synthetic exposure/range values.

## Failure and validation

On an acquisition/export failure, existing partial outputs are retained and
rehearsal.json records failed status/error. It does not erase prior runs. A failure
while writing the report itself may prevent that record; inspect the terminal error.
No new resume format or GUI is introduced.

```powershell
uv run --no-sync ruff check --fix examples/measurements/rehearse_spectrum.py tests/test_spectrum_rehearsal.py
uv run --no-sync pytest -q tests/test_spectrum_rehearsal.py
```

Eight focused tests passed in 32.99s in the review sandbox, including a fresh-process
rehearsal that forbids device/native/Qt imports. The real existing synthetic workflow
also ran successfully and produced 64 points with all seven checks passed. Ruff was
unavailable there; local lint remains required. No full-suite rerun is needed for this
example-only addition. No claim is made about the prior intensity-map visual rehearsal
unless the user supplies its outcome.
