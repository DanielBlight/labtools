# Independent camera window and dark subtraction

## Starting evidence

labtools_unified_evidence_20261119T133624085619Z.txt records HEAD
6f547acffd34935bf1953115d2a440bdd261d9a2 with the previous nineteen-path unified batch
APPLIED BUT NOT COMMITTED. Its local validation passed: Ruff, 220 tests (no skips),
headless launch and whitespace; source hashes are unchanged since validation. The
user reports the unified candidate worked, and camera preview on the lab PC lagged.
No measured camera FPS, frame dimensions, bit depth or latency trace was supplied.
Do not claim a measured hardware speedup or a clean committed unified checkpoint.

This camera batch layers on that exact pending source state. The guarded updater
also accepts a clean direct child commit containing exactly the prior nineteen paths
with matching source preimages. It refuses unrelated changes. The combined pending
commit is twenty-six paths; the camera-only delta is fifteen paths. No hardware
operations were performed during development. No experiment execution gate is removed.

## Use

Launch the native workspace as before. Open camera window is available above the tabs
and from Annealing. The camera window is modeless: move/resize it alongside mapping,
spectroscopy or annealing. Opening it never connects hardware. Press Start camera to
explicitly open the first available UC480 camera; its reported identity appears only
after connection. This request enables CAMERA PREVIEW ONLY, not map/spectrum/anneal,
laser output, shutters or stage motion. Standalone annealing uses the same popup.

Stop camera closes its operation-scoped handle on the same worker thread. Closing the
popup requests stop and defers hiding until cleanup. Reopening never auto-starts it.
Stop all includes camera; closing the workspace while busy requests stop and asks you
to close again after cleanup. No thread is forcibly terminated. An in-progress SDK
read can take up to the exposure/read timeout to return; a stalled native SDK cannot
be safely killed by this UI. Only one preview can reserve this workspace's camera
resource; preview does not reserve mirror/optical-path/stage/shutter resources and
can remain visible/live alongside any experiment tab. Separate processes are still
subject to the SDK's exclusive-device behaviour, not a cross-process registry.

Exposure, gain, display refresh and 16-bit white level are persisted through the
existing native-workspace preference mechanism. No connected state, dark image or
subtraction-enable state is automatically restored across application restarts.
The camera panel is no longer embedded in the annealing layout. Legacy preference
keys remain compatible; no local instrument profile/source recipe is changed.

## Lower-latency display path

The old preview already had a latest-frame slot; it was not an unbounded frame queue.
The new implementation retains that bounded design and removes other overhead:

- No artificial acquisition sleep; capture waits for the SDK's newest frame.
- Three SDK buffers instead of twenty; no change to the UC480 wrapper/SDK API.
- No per-frame image signals, full-resolution UI min/max or percentile normalization.
- Preview decimation and optional subtraction/8-bit conversion run on the camera
  worker, not the GUI. Only the newest immutable preview crosses a one-slot mailbox.
- GUI paints a QImage directly with aspect-ratio preservation, without building and
  scaling a QPixmap on every frame. BGR is displayed directly, not channel-reversed
  and copied to RGB first. Alpha is ignored consistently for preview/dark arithmetic.
- Status updates are throttled. Display FPS, post-read frame age and replaced-preview
  count help distinguish rendering backlog from exposure/SDK acquisition limits.

Post-read age starts when read_latest returns, NOT at sensor exposure time; it is
not an end-to-end latency measurement. Replaced previews are intentionally dropped
for responsiveness, not lost scientific acquisition records. This is a preview,
not a camera recording or calibrated measurement pipeline. Actual lab speed and
SDK compatibility still require a connected check. Exposure still bounds frame rate.

The display uses fixed levels rather than frame-by-frame auto-contrast. uint8 uses
0..255; uint16 defaults to white=65535. For a 12-bit signal stored in uint16, set
16-bit preview white level to 4095. This changes only display scaling, not raw data,
dark storage or camera settings. Preview downsampling is nearest-neighbour, chosen
for speed; it is not an image-quality-preserving export or analysis transformation.

## Dark subtraction

1. Start the camera with the required exposure/gain. Block illumination yourself.
2. Click Capture dark. The NEXT complete raw frame is copied at full resolution;
   this window does not operate a shutter, laser or stage.
3. Restore illumination and check Subtract dark. Signed subtraction prevents
   unsigned wrap; negative results display as zero. Raw camera arrays are untouched.
4. Clear dark removes it and turns subtraction off. Save dark (.npz) writes the raw
   frame with camera-context metadata for explicit reuse; it is not auto-loaded.

Alternatively Load dark image accepts Labtools NPZ, camera-native NPY, single-frame
TIFF, PNG, BMP or JPEG. Prefer NPZ/TIFF/NPY or lossless PNG. JPEG is lossy and not a
calibrated dark. Loaded images must match raw dimensions, channel count, dtype,
orientation and exposure/gain. No resizing, broadcasting or guessed bit-depth
conversion is applied. TIFF/PNG RGB are converted to camera-native BGR; NPY/NPZ are
already camera-native BGR (monochrome remains 2D). The UC480 wrapper's existing
horizontal mirror remains unchanged, so external darks must use that orientation.

Metadata-bearing NPZ darks check exposure, gain and reported device identity.
Other imported images are explicitly labelled acquisition-settings-unverified and
bound once to the first compatible live context. This is not proof they were
captured under matching conditions. A shape/dtype mismatch or later exposure/gain/
device change bypasses subtraction with a visible warning; recapture/reload instead
of silently applying an invalid dark. No exposure rescaling or automatic dark
reacquisition occurs. Saving an unverified imported dark does not certify its settings.

Dark arithmetic is done on raw values before display scaling. For speed, only the
pixels needed by the decimated preview are subtracted; pointwise subtraction commutes
with this sampling. Captured/saved darks remain full resolution. Preview subtraction
does not change spectroscopy darks, annealing output, map data or source provenance.

## Validate and accept

The updater --validate runs ruff check --fix, one focused camera/unified regression,
headless launch and whitespace checks, then writes an evidence snapshot in Downloads.
--snapshot refreshes source/Git state without rerunning tests. --paths prints the
exact combined staging list (unchanged previously committed paths stage nothing).
A skip is NOT Qt acceptance. Offline tests cover raw arithmetic, metadata/format rejection, bounded
mailbox, worker-thread ownership/cleanup, independent reservations and actual popup
render/start/stop/dark/reopen behaviour where Qt is available. No camera is opened
by the tests; native constructors are replaced with explicit test fixtures.

On the lab PC, check explicit Start/Stop, actual identity, exposure/gain, responsive
preview while switching tabs, Capture dark and loaded-image subtraction, settings
change invalidation, popup close/reopen and workspace stop/close cleanup. Record
FPS/post-read age at the same exposure, image dimensions and bit depth; do not infer
hardware performance from offline tests. Mapping/spectroscopy/annealing remain gated.
No packaging, ID900, anneal defaults/limits, shutter or stage algorithm changes.

## Actual development validation

Ruff check --fix passed on all thirteen camera-delta Python paths. The focused
selection returned 203 passed, 6 skipped in 262.70s, exit 0. All six skips are actual
Qt tests blocked by missing libGL.so.1 here, not accepted UI tests. The new camera
core initially passed 25 tests; final cancellation-before-start and independent
reservation/report checks passed separately (2 passed in 31.10s). Counts are not
combined into an invented full-run total. Headless launch passed without hardware.
No vendor import stubs were needed for this camera/unified selection. No camera
frame rate or connected-device latency was measured during development.

The updater fixture passed both supplied-pending-batch and clean-unified-commit
routes, exact twenty-six/fifteen staged paths, unrelated-change refusal, rollback
on whitespace failure, exact staging-list output and snapshot-only source-change
detection. Fixture metadata is not represented as real validation evidence.
The anneal acquisition/default contracts and UC480 wrapper are unchanged.
