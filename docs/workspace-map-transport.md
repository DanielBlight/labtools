# Workspace map transport boundary (development only)

This adds the synchronous counterpart to the spectrum transport boundary. It uses the
existing map provider, acquisition routine, cleanup actions and session reservations.
It does not enable a real workspace/CLI route or introduce persistent shared handles.

## Scope

`open_map_devices(config, factories=...)` now accepts an optional frozen
MapTransportFactories bundle: labjack(), counter(address), mirror(labjack, dio_pin=...),
and gate(labjack, pin=...). The bundle validates that every constructor is callable.
The existing no-factories real path still lazily imports the same wrappers and uses the
same ExitStack ordering. Simulation behaviour is unchanged; passing factories to a
simulation configuration is rejected, not silently ignored.

WorkspaceMapTransport requires that bundle, the existing ownership object and an
explicit configuration identity matching the workspace. It checks the map reservation
and real-contract configuration before creating transports. Its acquire callable is a
developer service-injection boundary, not wired into the simulation-only GUI.

All handles are created/used/closed inside the caller's synchronous acquisition worker.
Proxies reject calls from another thread or after provider exit. Existing acquisition
cleanup still attempts checkpoint, mirror home and gate close before counter/LabJack
context teardown. Lease release remains the caller's responsibility after worker
teardown; Stop alone never releases it. No calls are routed through the reservation
session's executor, and no second registry or ownership authority is added.

Factories are trusted executable Python, not a hardware sandbox. Only fake factories
are used for this development checkpoint. Real-contract settings are necessary to
exercise the native provider path, but fake test addresses/settings are not approved
physical configuration and no outputs are presented as experimental measurements.

## Failure semantics retained, not silently strengthened

ExitStack retains its existing exception chaining for counter/LabJack context-exit
failures. Tests verify both exits are attempted. They do NOT claim acquisition-error
identity survives every competing context-exit failure. Existing cleanup_actions
preserves the acquisition error when mirror-home/gate-close callbacks also fail.
This batch does not change native cleanup policy or physical ordering.

## Validate

```powershell
uv run --no-sync ruff check --fix src/labtools/runtime/map_devices.py src/labtools/runtime/workspace_map_transport.py tests/test_workspace_map_transport.py
uv run --no-sync pytest -q tests/test_workspace_map_transport.py tests/test_workspace_spectrum_transport.py tests/test_intensity_map_simulation.py
```

Sandbox focused result: 50 passed, no skips, 172 plotting-library deprecation warnings
in 48.61s. Fourteen new map tests exercise the actual provider/acquisition with fake
constructors, reservation/configuration refusal, synchronous worker affinity,
partial setup failure, cancellation/reuse, independent cleanup, context-exit attempts,
and wrong-thread/closed proxy rejection. Native imports are forbidden in that fixture.
The existing spectrum transport and simulation-map tests passed alongside them.
Ruff is unavailable in the sandbox; local lint remains required. No full-suite rerun,
hardware, Qt, packaging, ID900 or anneal execution/change was performed.

The preceding spectrum boundary snapshot verifies f25b5c8c5567bf7194e3c14c341ece70a39d129e,
its three-path commit and clean tree. No successful local terminal result accompanied
that snapshot; do not infer local validation solely from the commit.

## Remaining inputs

Before real unified controls: an approved map configuration identity and resource
mapping, authoritative device selection/addressing, wiring/pin assignments, operating
limits, native environment and connected-device acceptance. Reuse existing approved
profiles where available; do not treat defaults or test fixtures as approval.
The next integration should compose these two boundaries behind explicit configuration
and existing worker ownership, without forcing persistent connections or exposing real
controls before configuration/ownership is established. Historical 801-test evidence
remains at 235f70ca..., wheel/staging at 6074fdad..., startup-policy at 607c7db....
