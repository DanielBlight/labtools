# Spectrum processing refactor, 27 October 2026

> Historical batch/backlog note. Current implementation status and task order are
> authoritative in [architecture](architecture.md), [roadmap](refactor-roadmap.md)
> and [handover](ai-handover.md). Technical details below are retained for context.

## Delivered

- `processing/spectrum.py` owns the existing frame-reduction algorithm. Signal
  and dark acquisition delegate to it after their existing capture loops.
- `processing/dark_spectrum.py` owns DarkSpectrum and wavelength-checked
  subtraction. Existing imports from `acquisition.range_spectrum` remain valid.
- Range acquisition imports the vendor stitcher only when stitching is called;
  its type-only wrapper import no longer loads native dependencies on import.
- Importing the legacy hyperspectral runner no longer creates an output folder,
  imports hardware/plotting packages, or forces the process-wide Qt5Agg backend.
  Its default output directory is resolved when run() starts. OUTPUT_FOLDER is
  now None until explicitly overridden by a caller; it is no longer a computed
  import-time string. The caller/environment chooses the plotting backend.
- Offline regression tests cover combination math, dark/signal capture order,
  range dark-mode routing, reusable-dark capture, compatibility and import isolation.

## Preserved

GUI layout and signal wiring, persisted settings, map output/checkpoint formats,
laser and mirror limits, detector presets, signal/dark acquisition ordering,
and the single-pass mean/population-standard-deviation clipping calculation.
No new shared connection manager, main window or instrument simulation is added.

## Validation and limits

Run `uv run pytest -q` and `uv run pytest tests/test_spectrum_processing.py -q`.
Method-extraction tests exercise real wrapper methods without importing the
vendor SDK. Range tests replace the vendor stitch boundary. They do not prove
vendor stitching, Windows drivers, Qt rendering or real shutter timing.

The legacy hyperspectral experiment remains a hardware script with hardcoded
settings and incomplete failure-path cleanup. Its background capture does not
explicitly disable an already enabled laser. This batch does not change those
operations or certify the script for unattended use. Do not run it as a test.

Other inherited gaps remain, including the spectrum GUI allowing two median
frames while the wrapper requires three, and documentation referring to
acquire_frame/USB polling checks absent from this uploaded wrapper. These are
separate behaviour/API reviews, not silently repaired by this structural batch.

## Applying

Close GUIs and commit/back up current work. Put apply_labtools_spectra.py in the
repository root. `python apply_labtools_spectra.py --check` changes nothing.
`python apply_labtools_spectra.py --apply` checks the affected baseline and clean
tracked Git files, then backs up exact original bytes. It does not install
packages, run hardware or commit. Review `git diff` and run offline tests.

The installer prints a rollback command. Rollback refuses to overwrite subsequent
edits. The review patch is optional; do not apply both patch and installer.
