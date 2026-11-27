# Offline Analysis workspace

## Scope and architecture

The unified GUI has one Analysis tab. It is not in the acquisition-page registry,
receives no workspace/session object, and cannot reserve or operate hardware.
For an analysis-only process use `.venv\Scripts\python.exe -m labtools.analysis.gui`.

Modules:
- models.py: dataset tree, numeric shape/axis validation, read-only arrays.
- loaders.py: native/legacy NPZ adapters, retained dataclass-tree decoding, folders,
  sequences, synthetic examples, cancellable streaming NPZ-to-NPY memory mapping.
- processing.py: explicit processing state, maps, comparisons, spectra, bounded
  optional Gaussian fitting, metrics and colour scales.
- plotting.py: shared Qt/Agg figure renderer and linked map/spectrum presentation.
- exports.py: unique export folders, reproducibility recipes and source hashes.
- gui.py: dataset tree, specialised controls, metadata, paged raw arrays, loader
  ownership and main-thread Qt updates. Standalone launcher included.

No dependency or lockfile changes. Optional Gaussian fitting uses scipy only if
already installed (the existing optional analysis dependency). Missing scipy is a
clear diagnostic, not an implicit installation. No internet is needed on the lab PC.

## Loading

Open a native result folder, NPZ, metadata JSON, run.json, sequence.json,
program.json or retained-export folder. Dragging a local file/folder also works.
Open a common parent folder to compare independent measurements. One loaded tree
is owned at a time; failed loads preserve the current tree. Close dataset releases
mapped arrays and private temporary files. Large NPZ members (32 MiB and above)
are streamed into a private temporary directory and mapped read-only, because
compressed NPZ itself is not memory-mappable. Budget temporary disk space for the
uncompressed members. Cancellation is checked between 1 MiB chunks for large data.

Native formats inspected:
- acquisition/intensity_map.py: counts[channel,y,x], count_rates_cps, coordinate
  vectors, completed_mask, optional summed rates, metadata sidecar and checkpoints.
- io/spectrum_records.py: metadata JSON scalar, wavelength_nm, intensity and optional
  raw_intensity; saved dark mode is retained, not reapplied implicitly.
- acquisition/hyperspectral.py: metadata_json, x_v, y_v, wavelength_nm,
  intensity[y,x,wavelength], completed_mask and provenance.
- acquisition/run_hyperspectral_scan.py: legacy cube/x_mirror/y_mirror/wavelength.
- runtime/retained_results.py: run.json type/fields wrappers and array references
  into arrays.npz; no pickle and no reconstruction of live acquisition objects.
- runtime/focus_stack.py: all maps/sweeps, stage readbacks and coarse history;
  latest_progress is not duplicated when a final result exists.
- runtime/experiment_workflows.py: baseline-first sequence steps and moved output
  directories. Planned points are never treated as completed measurements.
- anneal metadata/result folders and retained runs: browse saved metadata/history.

Simplified synthetic fixtures are supported by explicit aliases/adapters. They
are not used as substitutes for invalid real files. Their hashes are verified by
the test fixture loader. Missing optional PNG files never prevent numerical loading.

## Working with data

Select a dataset or step in Datasets. Plot controls are filtered by dataset type.
Choose settings and click Apply plot settings. Reset restores unprocessed saved
intensity, no normalisation, no baseline subtraction and no fit. The saved
intensity itself may already be dark-corrected by acquisition; metadata records
that fact. Raw is offered only when genuinely saved. No smoothing/outlier rejection.

Maps: counts/rates, zero-based channel index or -1 for sum, manual/automatic/common
colour scales, linear/log, side-by-side, difference and ratio. Comparisons require
identical voltage grids; no silent interpolation. Invalid/incomplete pixels remain
missing. Ratio division by zero remains missing. Aspect is 0.75 Y per X without
changing the stored voltage coordinates. Hover reports pixel/voltage/value/status.

Focus stacks: every map is in the tree. Parent selection shows comparison metrics;
choose Trend for a metric versus requested_dc_v or saved index. Stage-before/after,
coarse history and all saved settings are in Metadata. gradient_rms is the RMS of
finite adjacent horizontal/vertical differences. It is not an absolute-focus claim.

Cubes: sum, band sum, trapezoidal spectral area, nearest saved wavelength, maximum
height or wavelength of the maximum. Lower/upper wavelength controls bound the
range; nearest-wavelength mode uses Lower wavelength as its target. Select a map
pixel to see its spectrum. Incomplete pixels show an explanatory message. Peak
width/area fitting is available for selected spectra and explicit fit_width/fit_area
parameter maps (bounded to 4096 acquired pixels; failed fits are counted and shown
as missing derived values, never removed from the raw cube). No raw cube is copied for ordinary row-wise derivation.

Spectra: saved/raw/dark/corrected when present, range selection, explicit maximum
or area normalisation, minimum or endpoint-linear baseline subtraction, optional
Gaussian-plus-constant fit and optional residuals for individual spectra. The fit
is bounded to the selected wavelength interval, positive amplitude/sigma and 5000
function evaluations. Flat/short/failed fits are diagnosed. A fit is not a claim
that a Gaussian is physically appropriate. Difference/ratio views require fitting
to be disabled, so raw-fit residuals are never mislabeled as derived-data residuals.

Sequences: browse saved steps/statuses chronologically. Select the parent for
spectrum overlays or Trend. Difference/ratio on a spectrum group uses the selected
reference, or explicitly the first saved spectrum if no reference was selected.
Trend metrics include spectral integral, mean/median/maximum, fitted centre/width/
area, and map summaries. Horizontal axes are saved index, saved cycle, explicitly
saved cumulative_dwell_s or requested_dc_v. Missing saved values are excluded with
reasons; planned dwell is never silently promoted to delivered dose. Baseline is
not assigned an invented cumulative dose if the export did not save one.

Raw arrays: choose an array and a starting row/column. Leading axes are flattened
only for the read-only table; the original shape and stored data are unchanged.
Each page is bounded to 100 rows by 32 columns. Non-finite values are labelled.

## Exports and recipes

Export plot + data creates a unique analysis-TIMESTAMP-ID folder outside the source
acquisition tree. It contains PNG/SVG/PDF, displayed_data.npz, CSV for spectra or
trends, plot_metadata.json and recipe.json. Source arrays are never overwritten.
The ordinary Matplotlib Save action is removed to prevent bypassing these guards.

Save plot recipe writes a new file only. Open recipe verifies source hashes and
recreates the selected node and settings. Relink recipe source handles moved source
files/folders with unchanged content. Retained arrays.npz and sidecars are included
in source identities. Missing/changed sources are rejected rather than substituted.

Batch export measurements traverses all numerical descendants of the selected
stack/sequence. For common map limits it calculates one shared range and uses it
for all maps. The batch also contains stack_data.npz and batch_index.json. Failed batches are
removed before publication; earlier completed batches remain untouched.

## Known limitations and acceptance status

This is a development candidate, not a fully Windows-accepted release.
- PyQt6 is unavailable in the implementation environment. Qt tests are supplied
  but were skipped here. Native Windows layout, interaction and integration need
  the bounded rehearsal below. No screenshot or GUI-runtime pass is claimed.
- Ruff is unavailable here; `python -m ruff check --fix` was attempted and failed
  with No module named ruff. It must run in the development environment.
- Existing tests/conftest.py has an unconditional QApplication autouse fixture.
  Core validation here used --noconftest rather than modifying that fixture or
  pretending Qt exists. Hardware tests were not run.
- GUI loading is asynchronous/cancellable. Derivation, recipe hashing and batch
  export are currently synchronous and can temporarily occupy the GUI for large
  datasets. They never run acquisition or operate hardware.
- Cube fit maps are explicitly bounded to 4096 acquired pixels and may take time;
  per-pixel failures are counted in plot metadata. No residual is shown by default.
- Trend axes use explicitly saved metadata. Native exports that lack delivered
  cumulative dwell cannot support a verified delivered-dose trend.
- CSV adapters support native named spectra (including synthetic comments),
  intensity-map point tables and anneal-position logs. Ambiguous matrix-only or
  unnamed CSV variants are rejected; prefer their native NPZ/retained outputs.
- Common scale currently applies to all matching map/cube nodes in the loaded tree,
  not an arbitrary multi-selection. Open a stack alone for stack-only scaling.
- No persistent recent-file list, automatic focus decision, automatic filtering,
  arbitrary interpolation, or modification of acquisition formats is introduced.

## Windows acceptance continuation prompt

Continue from the installed offline Analysis candidate. Inspect the current Git
status and the updater's exact changed-file list first. Do not redesign acquisition,
change instrument limits or operate hardware. Run Ruff with --fix and all relevant
new/existing tests using the real development environment. Record exact outcomes,
not estimated counts. Launch python -m labtools.analysis.gui and then the existing
unified simulation launcher. Rehearse all supplied examples and representative
real native map/checkpoint, retained focus-stack, spectrum, cube and baseline-first
sequence exports. Check 1150x780, 800x650 and a narrow 480x700 standalone window,
Windows display scaling, clipping, type-filtered controls, raw-table pagination,
wheel protection, map hover, cube pixel selection, fit/residual controls, failed
load preservation, cancel/close/reopen, shared colour limits and 0.75 map aspect.
Verify PNG/SVG/PDF and numerical exports, recipe replay/relink, source immutability
and unique batch outputs. Confirm Analysis makes no native-driver import or device
connection in its standalone process. Focus on observed acceptance failures only.
Address the explicitly documented synchronous large-data operations and bounded cube-fit
map performance as one bounded follow-up if required for release, not a
series of speculative micro-patches. Deliver a source-matched guarded updater,
exact validation evidence, Git commands and the next bounded continuation prompt.

## Analysis v2: recipes, calibration, background and peak models

- Recipes now identify a measurement by relative source path, kind and local
  location in the source record. A recipe verifies original source hashes and
  refuses changed collection/common-scale membership. Old single-file recipes
  with no comparison can be replayed if their identity is unambiguous. Reopen
  and resave old collection recipes rather than trusting their positional IDs.
- Darks open as calibration, including the stitched curve and saved native-centre
  segments. They are not signal spectra and are not subtracted again. The cube
  title and export metadata show the recorded reusable-dark stage if available.
- To subtract shared sample/optical background, pick a genuinely signal-free
  region of the cube. Enter `X min, X max, Y min, Y max` in mirror volts under
  Background ROI, then Apply. The wavelength-wise median of at least three
  completed spectra is subtracted at each pixel before deriving the map or
  processing a selected spectrum. The ROI is outlined and its spectrum is
  included in the exported NPZ and CSV. Clear the field to undo the correction.
  This is additive background removal, not a way to reconstruct raw detector
  frames or reapply the acquisition dark. Do not select a region containing a
  sample feature you wish to preserve. Do not assume a single template is valid
  where the background shape or intensity varies strongly across the scan.
- Fit models include Gaussian, Lorentzian and Voigt with a common constant
  offset and up to four positive components of the chosen model. Use a sensible
  wavelength window; for overlapping peaks, enter approximate centres in nm.
  Components are ordered by wavelength. The chosen component supplies fitted
  width/area map or trend metrics; fit metadata records every component of a
  displayed multi-peak spectrum. Fitted areas are full profile areas, not
  integrations restricted to the displayed wavelength interval. Fits use the
  existing optional SciPy package. A fitted component is not proof of a physical
  transition, especially for poorly separated peaks.
- Trend shared_mean uses finite acquired pixels common to the stack. Compare
  acquired fractions before interpreting totals from stopped maps. By default,
  signed differences and dark/background-corrected intensity use symmetric
  limits and a diverging palette. Log views mark acquired nonpositive pixels.
- Exports and recipe saves run as jobs and a batch reuses verified file hashes.
  Cancellation takes effect at checkpoints, not during an active image encode,
  compression, or fit. Apply can still take time for expensive fitted maps;
  clicking a point in an already-rendered cube only updates the linked spectrum.
