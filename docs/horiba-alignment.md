# HORIBA alignment v2

Changes: no repeat-interval setting. Exposure minimum 0.02 s for either detector.
Optional dark subtraction captures a fresh closed-shutter dark then a signal
at the same exposure for every update. Axes must match before subtraction.
Without subtraction, each update captures signal only. Negative corrected counts
are preserved. Captures run sequentially as fast as exposure, readout and SDK
communication permit; there is no intentional inter-frame delay. Display uses
a latest-only mailbox, so slow plotting may skip intermediate captures.

The wrapper gains an explicit minimum_exposure_override_s configure keyword.
Alignment passes 0.02; all other callers retain their original preset floors.
This is a software setting requested for alignment, not validation of shutter
accuracy at 20 ms. Verify closed/open frames on the actual SDrive/detector setup.
Another detector TTL may hold the shared shutter open. Stop is not an interlock.

Start/Stop still owns one worker thread and one asyncio loop. Stop during a dark
finishes that operation and skips the following signal. An active SDK call is
not forcibly aborted; inherited unbounded busy polling may delay stop. Closing
requests stop and defers closure until cleanup completes. Disconnect inherits
its existing limitations, including some internally suppressed close errors.
No laser, range scan, automatic save or slit movement is added. Presets may move
the grating/exit mirror. Close other HORIBA applications before starting.

Install: save apply_labtools_alignment_v2.py in the repository root, close GUIs,
then run --check and --apply separately. It accepts the exact previous alignment
release (or missing alignment files), checks the original wrapper baseline, and
backs up every changed file. Locally edited files are refused. Tracked changes
are allowed because this updater checks each affected file against its baseline;
it does not stage or commit anything. Keep the printed backup path.
Rollback: python apply_labtools_alignment_v2.py --rollback "BACKUP_DIRECTORY"
Rollback refuses to overwrite post-install edits.

Offline tests:
    uv run --no-sync python -m pytest tests/test_alignment_spectrum.py tests/test_alignment_gui.py -q
Launch:
    uv run --no-sync python -m labtools.gui.alignment_gui_horiba

Qt lifecycle tests require a working PyQt6 runtime. No real hardware validation
was performed here. The test spectra are fake fixtures, not measured data.
