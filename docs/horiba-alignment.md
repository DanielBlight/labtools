# HORIBA alignment

## Unified workspace integration, 2026-11-23

The accepted standalone stream is now embedded in the unified Alignment tab, using
one application-owned worker shared with the range panel and the existing Spectrum
workspace lease. Stop all and automatic deferred close include alignment cleanup.
Use [unified alignment](unified-alignment.md) for launch/acceptance instructions.
The earlier integration checklist below is retained as the design contract, not
an outstanding instruction to reimplement the same backend.


Status: current operational/API contract, updated 2026-11-22. The implementation
is repaired in source; Windows Qt and connected-device acceptance remain pending.

## Continuous session lifecycle

The alignment window calls `SpectrumWorker.start_alignment(settings)` once per
Start. `SpectrumService.run_alignment` opens/configures/positions one backend,
captures repeated frames and disconnects once when Stop, close or failure ends
the run. The same worker thread and asyncio loop own the entire session.
Settings are immutable for the run; stop and restart to apply changes.

The worker stays busy for the whole run, including teardown. Other jobs are refused
rather than queued between frames. The returned `AlignmentStreamJob` provides
`take_latest()` returning `(acquired_sequence, AlignmentResult)` or `None`, plus
`cancel()`, `done()` and `result()`. It retains at most one undisplayed frame.
A slow UI may skip display frames; this is not a lossless recording API. The
sequence reports acquired frames, not the number of canvas redraws.

`cancel()` requests cooperative Stop. It never interrupts a native SDK call.
`done()` becomes true only after cleanup and worker-state publication. Normal
Stop raises `asyncio.CancelledError` from `result()`; backend/cleanup failures are
preserved. A real failure faults the worker and requires application teardown.
There is no automatic reconnect or simulation fallback.

The one-shot `SpectrumWorker.acquire_alignment`, `SpectrumService.acquire_alignment`
and scripted `acquire_alignment_frame` APIs remain one-frame operations. They are
not continuous-session APIs and are intentionally unchanged.

## Detector and dark contracts

Exposure minima remain 0.065 s for Syncerity and 0.1 s for Symphony. No 20 ms
archive override is restored. With dark subtraction enabled, each frame captures
a fresh closed-shutter dark followed by signal, validating wavelength-axis agreement.
Raw and corrected arrays remain distinct immutable results. Presets can move
physical grating/exit-mirror hardware; use a reviewed optical setup.

## Ownership and window lifetime

An injected worker is application-owned and survives window close. A standalone
window creates a private worker and closes it only after active cleanup. Start
stays disabled through Stop/close teardown, including programmatic restart attempts.

Both real alignment and range adapters use the existing process-local HORIBA guard.
This prevents separate clients using these adapters from overlapping. It is not a
cross-process lock, a driver timeout, an interlock, or protection against unrelated
code constructing a native wrapper directly. Do not operate separate applications
against the same hardware concurrently.

## Unified GUI integration contract

The original standalone repair did not embed alignment. The 2026-11-23 integration
now uses `OwnedSpectrumPanel`/`HoribaRangeWindow` with a worker-backed service bridge,
and a workspace alignment panel injected with that same worker. The implemented
integration follows this contract:

1. Compose one application-owned spectrum worker/runtime for spectrum and alignment,
   or explicitly bridge the existing workspace ownership controller. Do not create
   another private native connection from a new panel.
2. Reserve the workspace spectrum resource for the entire stream and cleanup; retain
   busy refusal across mapping/Annealing where physical resources overlap.
3. Poll `take_latest()` on the GUI thread. Never access widgets in `publish_frame`.
4. Wire Stop all and deferred close to cancellation, then wait for job completion
   before releasing the workspace lease or closing the worker.
5. Keep real/simulation selection explicit and native-free in simulation. Resolve
   configuration identity from the reviewed existing source until the separately
   planned versioned instrument-profile migration is implemented.
6. Reuse this service/worker contract, not the old standalone device lifecycle.
   Add workspace ownership, Stop all and close tests before enabling real operation.

## Previous working GUI

The [archive note](history/horiba-alignment-v2-archive.md) identifies branch
`archive/horiba-alignment-v2`, tag `archive-horiba-alignment-v2` and commit
`9024b3adbd132bfb3db7ea8b83a803ffbd98f915`. That historical source is not contained
in this export. Its documented continuous workflow informed the target behaviour;
no historical implementation comparison or direct restoration is claimed.

## Launch and acceptance

The standalone module remains available with a maintainer-supplied
`LABTOOLS_SPECTRUM_CONFIGURATION_ID` in a reviewed real setup:

```powershell
uv run --no-sync python -m labtools.gui.alignment_gui_horiba
```

Simulation is available through the explicit `backend="simulation"` constructor.
This repair does not change standalone launch defaults or hardware commands.

Connected acceptance: observe one connect/configure/move per Start, multiple frames,
Stop and one disconnect, restart without reboot, dark on/off, close while active,
and competing spectrum refusal. Record exact candidate commit and configuration.
The earlier lab alignment FAIL remains open until this retest passes. See
[source audit](source-audit-2026-11-22.md) for executed tests and limitations.
