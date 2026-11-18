# Explicit workspace resources and injected services

The workspace remains simulation-only. The default configuration preserves the existing
single logical optical-path lease, map grid preferences and toy spectrum behaviour.
This is configuration/service wiring, not shared native connections or physical approval.

## Run

```powershell
uv run --no-sync labtools simulate workspace --config examples/workspace/simulation.json
```

Omitting --config uses the same defaults. The configuration is validated before Qt is
imported or a session is created. Real backends, unknown/missing/duplicate fields,
invalid resource references and invalid seed/timing values are rejected.

Schema version 1 includes configuration_id, backend, resources, map_resources,
spectrum_resources, simulation_seed and simulation_realtime. Resources are logical
simulation labels, not device addresses. Workflow resource names must be declared;
every declared resource must be used. Default both workflows reserve the same resource.
A deliberately disjoint simulation layout can reserve concurrently; that is not
permission for concurrent real hardware. No native resource topology is invented.

The existing InstrumentSession remains the only reservation authority. Its factories
are reservation-only and refuse device calls. No new registry, worker or native method
routing is added. Completion/cancellation/cleanup release paths are unchanged.

## Service injection for the next integration boundary

SimulationWorkspace now accepts config, map_acquisition and spectrum_service keyword
arguments. OwnedMapPanel passes the callable to the existing MapController; the spectrum
adapter passes the service to the existing spectrum window. Seed/realtime and spectrum
configuration identity come from the explicit configuration. The CLI exposes no Python
factory names, imports, device addresses or real backend selector.

Injected Python objects are trusted developer dependencies, not a security sandbox.
Use only simulation/fake services here. Their operations still execute through the
existing acquisition QThread and spectrum coroutine lifecycle. No native handle is
created or transferred to the reservation executor. The next real-device integration
must use approved configuration and resource-specific services while preserving affinity.

The configuration file does not contain scan grid values; the existing simulation
preferences continue to restore X/Y. Spectrum range/exposure defaults remain the toy
rehearsal values. Output root remains a separate CLI --output option.

## Validation

```powershell
uv run --no-sync ruff check --fix src/labtools/config/workspace.py src/labtools/gui/workspace.py src/labtools/gui/workspace_panels.py src/labtools/simulation/ownership.py src/labtools/simulation/workspace.py tests/test_workspace_config.py tests/test_simulation_workspace.py
uv run --no-sync pytest -q -ra tests/test_workspace_config.py tests/test_workspace_ownership.py tests/test_simulation_workspace.py
```

Sandbox focused selection: 39 passed, 2 skipped in 28.09s. Config/refusal/resource tests
and actual adapter constructor wiring against fake GUI bases passed. The two actual Qt
integration tests skipped because PyQt6 is absent, not because GUI acceptance passed.
Ruff is unavailable in the sandbox. Local lint and Qt tests remain required. No full
suite, hardware, packaging, ID900 or anneal execution/change.

Previous ownership batch is accepted on the user's instruction to assume local results
are good, not fabricated terminal counts. Its five-path commit and clean tree were
verified from the supplied snapshot. Historical test/package linkage is unchanged.
