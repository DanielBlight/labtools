# Alignment GUI timeout follow-up, 2026-11-23

Status: evidence-only follow-up to the persistent-session repair. Not Windows GUI
or connected-device acceptance. No new release or version bump.

## Observed Windows result

The supplied run collected 135 tests and stopped with **18 passed, 1 failed**.
The failure is `test_alignment_gui.py::test_injected_worker_repeat_stop_and_close`:
its five-second helper timed out while waiting for displayed sequence >= 2.
The other tests after this failure were not completed by that run.

The faulthandler snapshot shows the stream worker constructing/validating frames
(`detector_options`/deepcopy) while the main thread is formatting pytest's failure
traceback. That snapshot is not proof of a deadlock inside deepcopy. The test did
not have a finally block to stop the continuous worker after an assertion failed.
The Qt font-directory and propagateSizeHints messages are warnings in this log;
no evidence establishes either warning as the cause of the failed assertion.

## Confirmed source defects and bounded correction

The simulator's capture coroutine returns without a timed wait. The new persistent
service loop yielded with `asyncio.sleep(0)`, which lets other tasks on that worker
loop run but does not rate-limit the worker thread or guarantee Qt thread fairness.
The single-slot mailbox bounded memory, not acquisition CPU consumption. This was
an omission in the original repair. It can cause GUI contention, but the exact
Windows timeout cause is not established by the Linux reproduction alone.

A local reproduction using the reconstructed previously delivered service and the
supplied simulator produced 3,263 frames in 0.5 seconds. After this follow-up it
produced five with the default 0.1-second exposure. These are local illustrative
measurements, not Windows performance claims or hardware timing measurements.

Changes:

1. Pace only `run_alignment` with backend `simulation`, using the requested exposure
   as an inter-frame display delay. The first frame remains immediate. This is a
   synthetic display cadence, not a physical detector/shutter timing model.
2. Split the wait into at most 50 ms asyncio sleeps and check cooperative Stop between
   them, so a long simulated exposure does not impose a full-exposure Stop delay.
   This is a polling interval, not a guaranteed wall-clock response deadline.
3. Keep the real stream's existing zero-delay yield and native capture lifecycle.
   No detector limits, SDK timing, hardware commands, dark ordering or ownership
   rules are changed. Scripted one-shot simulation is not paced.
4. Add a finally block to the failing GUI test to request Stop, pump completion and
   close the injected worker even when an assertion fails. Keep the original
   five-second helper deadline and assertions; do not hide the failure by increasing
   timeouts or skipping the GUI test.
5. Add four Qt-free regressions: positive simulation wait and Stop during that wait;
   no positive delay in real mode; Stop from frame publication skips waiting; and
   unchanged one-shot simulation behaviour.

The service remains Qt-free and reusable by the future unified GUI. Pacing is not
implemented in a standalone widget or by opening another device session.

## Validation actually performed

- Four new pacing tests plus the existing spectrum-service module: **60 passed**
  in an isolated Qt-free selection. The project-wide autouse QApplication fixture
  was not run. Existing subprocess import isolation used a source-path link to
  preserve its relative source lookup.
- Available Ruff 0.11.13: the three changed/new Python files passed `check --fix`.
  This is not the project's locked Windows Ruff version.
- Syntax compilation passed for the three Python files.
- The service was reconstructed from the previously delivered method and supplied
  source; this session does not have the user's current edited checkout. The
  updater compares the affected functions' ASTs before applying, tolerating
  formatting changes but refusing unexpected functional edits.
- Updater preflight, apply, repeat application, conflicting-function refusal and
  rollback were tested in a temporary Git checkout.
- Windows Qt test, full 135-test selection, full non-hardware suite and connected
  HORIBA acceptance remain unverified. Do not mark the earlier GUI failure closed
  until the Windows test passes.

## Application and validation

Apply `install_alignment_gui_pacing_20261123.py` from the development checkout.
It requires the previous persistent-session repair. It backs up all changed targets
under `.labtools-refactor-backups`, supports guarded rollback and does not stage,
commit, connect to hardware or run tests automatically. Do not rerun the original
installer over this follow-up.

Run the failing GUI test together with the new pacing tests first. If it passes,
run the full targeted selection, now including the pacing module. If it still fails,
retain the first failure and worker state; do not install fonts, relax deadlines or
change hardware timing based solely on the warnings.

## Next bounded continuation prompt

Continue from the persistent-session repair plus the 2026-11-23 simulation-pacing
follow-up. Inspect actual Git status and the new Windows test result. First close
any remaining failure in test_injected_worker_repeat_stop_and_close without hiding
it behind a longer timeout or weakening assertions. Keep cleanup in finally and
simulation-only pacing; do not change real hardware timing. Once the targeted Qt
selection passes, record one connected alignment Start/multiple-frames/Stop/restart
observation against the actual commit and configuration. Then integrate the existing
Qt-free stream into the unified workspace with one application-owned runtime or
explicit workspace ownership bridge, Stop all and deferred close through teardown.
Keep the strict flat instrument profile unchanged and the versioned profile migration
separate. Deliver one bounded updater only if evidence requires code changes, exact
validation results, Git staging/commit commands and the next bounded prompt.
