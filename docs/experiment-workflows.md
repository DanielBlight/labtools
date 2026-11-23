# Unified anneal programs, hyperspectral maps and sequences

## Consolidated workflow update, 2026-11-23

Current operation: one Annealing tab, independent live hyperspectral grid, Alignment
popup from Spectrum, and optional-output sequences with one baseline measurement
then one anneal/measurement pair per cycle. The old phase-count controls and separate
Anneal programs/Alignment tabs are superseded. See
[operation and evidence](workflow-ux-baseline-20261123.md). New Windows/connected
acceptance remains pending; prior baseline records are unchanged.


Implemented behind the existing explicit --simulate and --hardware launch modes.
The default-disabled and --hardware-spectrum modes are unchanged. No instrument
profile schema, approved limit, dependency or automatic laser-ON behaviour changes.

## Anneal programs tab

The original Annealing tab remains unchanged for its accepted uniform scan. The new
Anneal programs tab uses that tab's grid coordinates, passes, settle, stage settings
and output path, with its own first/single dwell, last dwell and spacing controls.

- Single point: X start / Y start, specified dwell, repeated for the selected passes.
  Stop coordinates and grid counts are ignored for this mode.
- Dwell ramp array: the existing grid/traversal, with first and last dwell endpoints.
  Linear uses a constant time increment; Logarithmic uses a constant time ratio.
  Intermediate dwell i is first + i/(N-1)*(last-first), or
  exp(log(first) + i/(N-1)*(log(last)-log(first))). Endpoints are exact.
- Uniform array: same grid/traversal with the first dwell at every point.

The ramp follows actual row/serpentine traversal order, not the physical X index;
it restarts for each pass. Increasing and decreasing ramps are supported. A one-point
ramp requires equal endpoints. Linear permits zero dwell; logarithmic endpoints
must be strictly positive. All values must be finite/nonnegative and every dose is
validated against the existing source/local profile before hardware opens. The sum
of programmed dwell and settle across all passes must fit the existing maximum
open-time budget. A maximum of 100000 point exposures bounds plan construction.
Preview point doses shows coordinates/dwell before Start (first 1000 lines only).

Each point deliberately uses the existing complete one-point Annealing acquisition:
shutter readiness/close, stage to anneal coordinate, mirror/settle, shutter dwell,
shutter close, mirror home, stage return if configured, and connection cleanup.
This adds stage/connection overhead BETWEEN points. It does not promise a fixed
inter-point cadence or nanosecond shutter timing. Dwell is the requested shutter-open
wait, not total elapsed point time; physical opening/closing and SDK latency remain.
No beam-open travel between points is introduced. Existing original uniform scanning
is still available when that established scan behaviour is wanted.

program.json records the complete ordered coordinate/dwell plan and progress/status;
each point has a unique child output directory. Stop/failure prevents later doses.
No automatic laser output/power change is performed.

## Hyperspectral tab

Uses a snapshot of the Intensity map grid and settle time plus the Spectrum tab's
range, preset, detector, exposure, combination and readout settings. Dark mode is
explicit: none, per_center or per_frame. Reusable pre-taken dark is not exposed here.
The cube uses the existing hyperspectral acquisition/archive implementation and the
SAME application-owned SpectrumWorker as range/alignment. One configured spectrum
session is held for the whole cube, not a new native connection per pixel.

Both map and Spectrum resources are reserved for the complete operation. The mirror
and native spectrum handles are created/called/cleaned on the spectrum owning thread.
No IDQ count acquisition or SPAD-gate control is needed for a spectral cube. Mirror
home is attempted before releasing the LabJack. A native operation/cleanup failure
faults further hardware work until application teardown. Laser OFF/disconnect remain
available. Existing first-device selection limitations remain.

Start saves cube.npz in a unique directory. It contains wavelength, X/Y axes, spectral
cube, completion mask and provenance. Stop retains partial data when the existing
service can produce it; unvisited pixels are displayed as missing, not zero. The
integrated-intensity image is selectable: click a pixel to display its spectrum.
The plot has the standard navigation toolbar. Live progress is latest-only/bounded;
the final/partial cube is rendered on completion. Existing archive/view APIs remain.
No cube resume, automatic laser-ON or new physical calibration is added.

## Sequences tab

Each cycle performs:

1. The selected Anneal programs plan, repeated Anneal programs / cycle times.
2. The selected measurement, repeated Measurements / cycle times.
3. Repeat the complete cycle Cycles times.

Measurement choices are Spectrum, Intensity map and Hyperspectral. This is a fixed
anneal-then-measure sequence, not an arbitrary scripting language. Settings are
snapshotted at Start from the relevant tabs. Editing a control during a run affects
only the next run. Return rotation stage must be enabled so a measurement cannot
silently follow a program left at the annealing coordinate.

One exclusive union lease is held across the ENTIRE sequence, including phase gaps.
Context-local borrowed step owners authorize only the sequence operations; unrelated
threads/panels cannot borrow the reservation. Existing range/alignment, map and
Annealing validation/cleanup paths are reused. The native spectrum worker remains
the sole owner of its native handles. Apply current/Output ON conflict with the
optical lease; OFF/disconnect and global Stop all remain available.

Stop is cooperative: finish/clean up the active operation, then do not start another
point, measurement or cycle. Failure aborts the sequence rather than continuing.
Closing the application requests Stop and waits for worker completion/cleanup. It
does not forcibly terminate a vendor call and is not an emergency stop.

A unique sequence directory contains sequence.json with the settings snapshot,
ordered completed/cancelled steps, outputs and final status/error. Each cycle/phase/
repeat gets a distinct child directory. Spectrum saves wavelength/intensity NPZ;
intensity maps use their existing full output; hyperspectral uses its existing NPZ
archive. Spectrum sequence measurements use no dark subtraction in this batch; the
standalone Spectrum tab's cached-dark and CSV/PNG choices are not reused. No output file is silently overwritten. A failed sequence is not resumable
in this batch. The operator chooses laser state/power explicitly before starting.

## Settings and layouts

Workspace export/import and startup preferences include the new program mode/dwell/
spacing, cube dark/output and sequence counts/measurement/output. Existing grid and
spectrum fields remain source-bound. Loading settings does not start a run or enable
laser output. Full plan validity is checked again at Start; imported endpoint/count
combinations can be incomplete drafts until corrected.

Camera form labels/fields wrap and expand instead of retaining narrow fixed widths.
The intensity-map layout reserves renderer-measured Y-label/tick space and shrinks
the map area, not the margin, when narrow. No acquisition timings are changed by
these presentation corrections. Confirm Windows DPI/font behaviour on the lab PC.

## First rehearsal and connected checks

Use --simulate first: single point; a 2x2 linear ramp; a positive logarithmic ramp;
a 2x2 cube and pixel selection; two-cycle sequences for each measurement; Stop all
and active close. Check saved plan/cube/sequence outputs and settings round-trip.
Then commit/push the exact validated revision and use --hardware on the lab PC with
the existing reviewed local Annealing profile. Use the reviewed optical setup and
physical interlocks. Stage movement/Annealing can change delivered power/open the
shutter. Keep the existing 0.040 A laser policy. Test small jobs before long repeats.
The preceding unified GUI pass does not cover these new workflows.
