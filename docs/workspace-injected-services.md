# Resource-specific injected simulation services

This batch exercises the existing workspace injection boundary with the existing map
and spectrum simulators. It does not add another simulator, resource registry, worker
executor or native connection. All four files are additions; existing production paths
and normal workspace launch remain unchanged.

## Launch the injected variant

```powershell
uv run --no-sync python examples/workspace/run_injected_services.py --config examples/workspace/simulation.json
```

Use the existing map and spectrum tabs. Complete a map, capture/subtract a spectrum
dark, repeat, and test Stop all during a sufficiently long map. The normal workspace
conflict/cleanup rules apply. Close when idle. The terminal prints the most recent
4096 resource events (diagnostic only, not a complete durable audit or acceptance).

The same service bundle is injected into the existing MapController and spectrum
window. It binds to the workspace's existing ownership object before any operation.
No second reservation authority is created. Unbound/unreserved operations and real
backend requests are refused. Owner-label checks are trusted developer diagnostics,
not a security boundary or substitute for a reservation token.

Map mirror/gate/counter proxies are created and used inside the existing acquisition
worker. Each call checks its operation thread and lifetime. Spectrum detector proxies
are created, used and closed inside the existing spectrum coroutine's thread/event
loop. Repeated operations reuse the service object, not backend handles across loops.
Resource close events precede the GUI's lease release at worker teardown. A cancellation
request does not release the workspace reservation prematurely.

This demonstrates shared service-instance reuse and operation-scoped affinity. It does
NOT demonstrate persistent shared native connections, native fault recovery or a
physical resource topology. Existing InstrumentSession remains reservation-only here;
no acquisition is moved onto its executor. No real backend selector is exposed.

## Focused validation

```powershell
uv run --no-sync ruff check --fix src/labtools/simulation/workspace_services.py examples/workspace/run_injected_services.py tests/test_workspace_injected_services.py
uv run --no-sync pytest -q -ra tests/test_workspace_injected_services.py
```

Ten new non-Qt tests passed; the actual injected Qt workflow test skipped in the
sandbox because PyQt6 is absent. Combined with existing workspace config/ownership/
composition tests: 49 passed, 3 skipped in 38.38s. Skips are not GUI acceptance.
The new Qt test forbids native imports, injects the real service bundle, tests conflict
and cancellation, then verifies actual resource events are off the UI thread and that
spectrum operations remain on one thread/loop through closure.

Ruff is unavailable in the sandbox. Local lint and the new Qt test remain required.
Do not rerun successful full-suite evidence to recover counts. No hardware, packaging,
ID900 or anneal changes are made. Historical source linkage remains unchanged.

Previous configuration batch source/commit scope is verified; no new local terminal
results were supplied with the snapshot, so its local validation is not fabricated.
