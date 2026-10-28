# Current architecture

This document describes the audited 28 October 2026 source, based on snapshot HEAD
`3e5a0c9f41edbbf692faabd9ef5cd6e9b2bc8aab`. Actual Git status is authoritative.
See [handover](ai-handover.md), [roadmap](refactor-roadmap.md) and
[audit](comparative-audit.md) for evidence and limitations.

## Package boundaries

- `cli.py` / `launchers.py`: lazy standalone dispatch, not a shared launcher.
- `config/`: validated requests, profiles and recipes; native-free HORIBA option tokens.
- `devices/`: physical wrappers; native imports remain inside real composition where possible.
- `runtime/`: session ownership, narrow services, providers and spectrum loop worker.
- `acquisition/`: measurement orchestration, cancellation, records and map checkpointing.
- `processing/`: Qt/native-free numerical transforms and legacy dark arrays.
- `io/`: pickle-free versioned spectrum/dark NPZ persistence. Keep this package.
- `simulation/`: explicit deterministic toy backends, not calibrated instrument models.
- `gui/`: Qt controls/controllers, settings snapshots and plotting of returned data.
- `visualisation/`: plotting and colour transforms.

Map persistence still lives in `acquisition/intensity_map.py`. Extracting it to `io/`
is deferred until a separate schema-/resume-compatible checkpoint, not mixed into this audit.
Compatibility exports remain in `operator_cli`, `gui.background`, `config.recipe_ui`
and `simulation.map_backend`; external users have not been inventoried for removal.

## Shared synchronous ownership

`InstrumentSession` is the process-local reservation authority for registered physical
resources. Mirror and gate alias one `labjack`. Factories, commands and close execute
on its worker. Whole-map reservations include checkpoint/home/gate cleanup. Faulted
normal commands are rejected; reviewed argument-free cleanup remains allowlisted.
Status snapshots are detached diagnostics, not authorization. Release does not close.
Shutdown refuses active leases and attempts all opened resource closes independently.
Zero-voltage home is movement, not a certified safe state. Native calls can block.

`SharedMirrorMapApplication` injects `ManualMirrorService` and `SharedMapProvider`.
Manual connect reserves without motion; disconnect releases only the lease. Shared
mode omits uncoordinated ITC laser control. Standalone tools do not join this session.

Real composition registers one fixed `time-controller:<canonical-IPv4>` count service
alongside LabJack. Maps reserve both atomically. IDQ construction/connect/configure/
count/disconnect stay on the session worker. Partial connect failure attempts cleanup
and retains its original error. The shared address policy is intentionally narrower
than general socket hostname resolution: no DNS alias equivalence is claimed. Multiple
addresses are possible in the session foundation, but this application exposes one
fixed controller, not dynamic multi-controller discovery. DLT/histogram/stream ownership
is not migrated. The legacy wrapper may swallow some disconnect errors internally.

Simulation composition owns one synthetic mirror/gate state; counters remain per-map.
Failure-injection measurement count resets per map. Position/gate ownership persists.
`gaussian-scene-v1`, coordinate/channel seeding, schema 1 and resume signatures remain
unchanged. Real failures never select simulation. Diagnostic snapshots are not hardware
readbacks and do not certify calibration, timing or interlocks.

## Spectrum service, records and loop ownership

`SpectrumService` is canonical orchestration for range and single-centre alignment.
Range operations produce immutable `SpectrumResult`/`DarkRecord` with configuration
identity. NPZ is authoritative; CSV/PNG are derivatives. Legacy CSV cannot acquire
provenance by attaching current settings. Fresh-dark range results may have no raw
array; alignment explicitly retains both raw and corrected arrays in `AlignmentResult`.
Alignment is a separate single-centre result contract, not a range SpectrumResult.

`SpectrumWorker` is an explicit job executor, not a second general device registry.
It owns one lazy thread/asyncio loop and rejects concurrent complete jobs. States are
unopened, starting, available, busy, faulted, closing and closed. It does not own a
persistent HORIBA connection: each service job still connects/configures/operates/
disconnects on that loop. Separate worker instances are not mutually exclusive; only
clients injected with the same worker coordinate. There is no cross-process exclusion.

Request/backend mismatch is rejected before worker startup. Startup failure is
published to callers; close/start races are serialized and self-join is rejected.
Shutdown refuses an active job, then drains tasks/async generators/default executor,
closes the loop and joins the thread. A blocked SDK/default-executor call can still
block shutdown. No forced interrupt or bounded deadline is claimed.

Cancellation is cooperative before opening and after a complete backend operation,
not per-frame or inside native calls. Busy ownership lasts through context cleanup.
Real operation failure faults the worker. Cancellation with failed real disconnect
also faults it while retaining CancelledError and cleanup notes. Teardown/reconstruction
is required; no automatic reconnect or synthetic fallback exists.

## GUI ownership and alignment

The ordinary spectrum GUI retains its existing operation-scoped AsyncTaskRunner and
standalone lifecycle; it does not automatically share SpectrumWorker with alignment.
Alignment snapshots settings on the UI thread and submits sequential jobs through the
worker. A Qt timer polls job completion; no raw vendor/loop object enters GUI code.
Injected workers survive tool close; private standalone workers close after active
cleanup. Busy is recoverable; real faults require application teardown. Stop/close
waits for the job boundary. Alignment repeats full connect/disconnect jobs, so no
high-rate persistent-connection performance is promised.

Native-free `config.horiba_presets` supplies the same gain/speed/default tokens to the
wrapper and alignment controls. Syncerity minimum is 0.065 s; Symphony minimum is
0.1 s. Alignment validation and both adapters enforce backend selection and exposure
floors without a 0.02 s override. No slit/ROI/grating commands were changed by this audit.

## Evidence and outstanding work

Offline fakes test orchestration, not SDK behaviour. QtWidgets tests are present but
were skipped in the audit environment. Physical LabJack, IDQ, HORIBA, shutter timing,
voltage calibration and optical safety remain unvalidated. Shared launcher integration,
wrapper failure reviews, operator-profile generalization and additional simulation
remain planned. Do not merge solely because headless tests pass.
