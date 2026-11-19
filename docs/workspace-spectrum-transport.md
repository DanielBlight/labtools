# Workspace spectrum transport boundary (development only)

The injected simulation-service batch at 485c3977029a2b102fbdda04a54b956771f26506
is closed by the user's confirmation of local validation/rehearsal. This addition
moves one workflow from the toy backend contract to the existing native adapter
contract, while using fake transports only for development validation.

## Scope

WorkspaceSpectrumTransport takes the existing workspace ownership object and an
explicit spectrometer_factory. It exposes a SpectrumService using the existing
open_real_range adapter, which already owns connect/configure/acquire/disconnect,
range acquisition and competing-disconnect failure preservation.

There is no default factory, real GUI launch, CLI hardware route, approved profile,
new registry or change to existing native adapters. The simulation workspace remains
unchanged. This is a developer integration boundary, not operator hardware enablement.
A supplied Python factory is trusted executable code: supplying a native factory
manually could access hardware. Do not do that during this development checkpoint.

The adapter requires real-labelled SpectrumSettings because that is the existing
native-adapter contract. In the tests these settings describe only a fake transport;
no result is exported as experimental data. The example numeric values and preset
are test inputs, not approved physical settings.

Before constructing a transport, it checks configuration identity and that Spectrum
owns its declared resources through the existing session authority. The caller keeps
that reservation until worker teardown; this boundary does not release it itself.
Owner-label checks are trusted developer guards, not a security boundary/token system.

Each operation constructs its transport inside the calling coroutine, and disconnects
inside that same thread/event loop. Service reuse does not reuse native handles across
loops. Proxies reject use after exit or from another thread/loop. Existing disconnect
error preservation applies to acquisition errors and asyncio cancellation.

## Development validation

```powershell
uv run --no-sync ruff check --fix src/labtools/runtime/workspace_spectrum_transport.py tests/test_workspace_spectrum_transport.py
uv run --no-sync pytest -q tests/test_workspace_spectrum_transport.py
```

Fourteen tests passed in 6.81s in the review sandbox, without Qt or native SDK imports.
They use a fake spectrometer transport but exercise the actual open_real_range adapter
and range centre/capture lifecycle. The SDK stitching function is replaced with an
explicit one-centre identity stitch/filter test double; stitching correctness and SDK
compatibility are not established. Native imports are forbidden in the test fixture.

Coverage: refusal before factory construction; conflict/config identity; per-operation
worker thread/loop identity; dark capture/subtraction; cancellation before/inside
acquisition; failed connect/configure/acquire with failed disconnect; disconnect-only
failure; closed/cross-loop proxy rejection; cleanup before reservation release; reuse.

Ruff is unavailable in the sandbox. Local lint remains required. No Qt tests are needed
for this boundary-only addition. Do not repeat the accepted full suite to recover counts.
No hardware, packaging, ID900, anneal, map native integration or GUI changes are made.

## Remaining external inputs and next integration

Real operator enablement still requires an approved spectrum configuration identity,
authoritative preset/device selection and optical-path procedure, intended native
SDK/driver environment and connected-device acceptance. No such values are invented.
Map native integration remains separate: its synchronous LabJack/counter/mirror/gate
ownership must be explicit, not forced through the spectrum coroutine lifecycle.

The next software step is the equivalent explicit map transport-factory seam, using
fake transports and the existing map provider. Do not expand this spectrum batch or
force persistent connections. Preserve historical source linkage: 801-test evidence
at 235f70ca..., wheel/staging at 6074fdad..., startup-policy validation at 607c7db....
