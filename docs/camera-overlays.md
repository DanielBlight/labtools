# Camera overlays and explicit synthetic preview

## Use in the workspace

Open camera window as before. The new source selector defaults to **Simulated camera
(no hardware)** on each application launch. Press Start camera for a synthetic
640x480 monochrome uint8 feed with moving spots, fixed-pattern background and noise.
The title, source notice and painted watermark identify synthetic data. Exposure and
gain affect this synthetic signal; they are not physical readbacks. No native camera
module is imported and no physical camera resource is reserved for simulation.
There is no automatic fallback from failed real hardware to simulation.

To use the real camera, stop the feed, choose Real UC480 camera, then press Start.
The existing real-camera factory, operation-scoped worker, reservation, dark processor
and cleanup are reused unchanged. Source switching is disabled until cleanup finishes.
Switching source clears the previous frame/dark/annotations. New connections clear
annotations because a new camera connection is not proof of spatial registration.
No map/spectrum/anneal execution gate, local profile, voltage limit or device identity
is changed. No hardware operations were performed during development.

## Standalone development launch

```powershell
uv run --no-sync python -m labtools.gui.camera_tools --simulate
```

This opens only the camera window; no manifest or lab instruments are needed. Press
Start camera. The --simulate flag documents the intended mode; simulation is also
the default without it. The source is never automatically started or persisted.
This is a development preview, not connected-camera acceptance or measurement data.

## Crosshair and concentric circles

Crosshair and Concentric circles can be toggled independently. Both are centred on
the image centre, not the window centre including letterbox margins. Set ring spacing
in raw image pixels and ring count (1..20). These are display-only alignment guides,
not calibrated physical dimensions. They are painted over the preview without
modifying raw frames, saved darks, subtraction, exposure/gain or experiment data.

## Annotated circles and Undo

Enable Draw annotated circles. Optionally enter a label, then drag from the desired
centre to the circle edge inside the image. Empty labels become Circle 1, Circle 2,
etc. Each circle shows its label and radius in raw pixels. Annotations stay anchored
when the window resizes and are clipped to the image, not drawn over letterbox areas.

Undo annotation removes the latest completed circle. Clear annotations is also
undoable. Ctrl+Z works when the image surface has focus; normal text-field undo is
not intercepted. Escape cancels a drag before completion. Releasing outside the image
cancels the circle. Maximum 200 circles, 200 undo steps and 80 characters per label.
A raw image-size change clears annotations instead of silently stretching them.
Overlays/annotations are session-only: hide/reopen the same stopped popup retains
controls, but a new connection clears circles and application restart resets them.
No annotation export or physical pixel-size calibration is claimed by this batch.

## Test dark subtraction with simulation

1. Start the simulated feed and choose exposure/gain.
2. Check Simulated dark scene, wait for the display to settle, then Capture dark.
3. Check Subtract dark; the dark scene should become nearly black (noise remains).
4. Uncheck Simulated dark scene; the moving synthetic spots should remain visible
   above the corrected background.
5. Change exposure/gain to check that the existing compatibility warning bypasses
   an incompatible dark. Capture a fresh dark at the new settings if required.

Simulated dark scene affects only synthetic illumination. It never operates a real
shutter, laser or stage. Real dark capture still requires manually blocked illumination.
Dark subtraction is upstream of overlays, so crosshairs/circles cannot be captured
into a raw dark. Loaded real-camera darks and synthetic darks have different device
contexts and are not silently treated as interchangeable.

## Scope, installation and evidence

Eight paths: three new modules, two tests, this guide, and two existing consumer
imports switched to the enhanced window. The existing base camera_window.py,
camera_stream.py, camera_preview.py and camera_dark.py are unchanged. This is an
explicit subclass extension, not a monkeypatch, duplicate acquisition loop, new
registry or experiment activation. The existing latest-frame mailbox is reused.

No fresh snapshot accompanied this request. The user's confirmation establishes
that the previous popup looked good, not current Git state or measured performance.
The updater reads the previous downloaded apply_labtools_camera_preview_v1.py as
AST literal data only (never executes it), checks the installed camera-source
preimages, and changes only the eight listed paths. Keep that previous installer in
Downloads. It accepts the prior work whether pending or committed, without inventing
a current commit hash or claiming a clean tree. Unrelated local files are not staged
by the provided commands; earlier unified/camera changes are included if pending. Local source/profile/provenance and historical evidence
remain unchanged; the existing native execution gates and anneal defaults are intact.

--validate runs ruff check --fix, one focused overlay/camera/unified regression and
headless launch, writes an evidence snapshot outside the repository in Downloads,
and returns nonzero for failures/skips/source changes. --snapshot refreshes evidence
after commit without rerunning tests. --paths prints the exact combined 32-path staging list, including prior unified/
camera work if still pending. Previously committed unchanged paths stage nothing.
Review source text for sensitive content before uploading. Qt skips are not acceptance.

Actual sandbox validation: 21 passed, 1 Qt skip in 6.40s for the new annotation and
simulation selection. The Qt skip is missing libGL.so.1, not a passed interaction test.
Ruff check --fix passed after import-order and context-manager formatting corrections.
No current user repository, hardware, end-to-end popup rendering or baseline camera
regression was executed in this sandbox for this batch. Local validation includes the
actual drag/render/undo/dark/source-switch/cleanup test and existing camera regressions.

The updater fixture passed preimage-edit refusal, eight exact changed/staged paths,
consumer-import wiring, rollback on a payload whitespace failure, and verification
that the previous installer is parsed as literal data rather than executed. These
are fixture checks, not claims about the user's current Git tree.
