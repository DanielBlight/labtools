# Unified simulation workspace: operation ownership

Launch with `uv run --no-sync labtools simulate workspace` as before. Both existing
panels, output handling, cooperative Stop all and close-during-acquisition remain.

## Map settings memory correction

The previous shell explicitly set X/Y points to 5 after the map panel had restored its
preferences. Those two assignments are removed. The map's existing isolated simulation
settings now determine X/Y points on reopen. No new settings store is added. Settings
are saved by the original map close handler when the workspace closes successfully.
An attempted close while acquisition is active does not save/close the panel yet.
Output roots are still chosen by the workspace launch root; this batch fixes the grid,
not workspace output-root persistence. Spectrum defaults remain unchanged.

## Operation ownership

Workspace-only adapters reserve one logical `simulation-optical-path` resource using
the existing InstrumentSession. This explicitly serializes map and spectrum operations
in this rehearsal shell. It is a logical conflict demonstration, not a claim that the
two native workflows necessarily share every device. No physical resource inventory,
second registry, device factories or hardware ownership policy is invented.

- Map start/resume reserves before worker start. Validation refusal/start failure releases.
- Spectrum connection test, dark capture and acquisition reserve before worker start.
- A conflicting operation is rejected in that panel's status with the current owner.
  It is not queued or silently started later.
- Stop requests do not release ownership. Map releases on the existing controller idle
  signal after QThread teardown. Spectrum releases after its existing thread-finished
  cleanup. Completion, failure and cancellation use those same teardown paths.
- The header shows the owner including cleanup. Close remains blocked while workers
  are active; the session closes only after idle panels have closed.

The session is reservation-only: no `.call()` routes acquisition through its executor,
and its resource factory refuses calls. Existing map and spectrum workers retain their
thread/async-loop affinity. Standalone GUIs and the InstrumentSession implementation
are unchanged. This is not real-device connection sharing, an interlock or cross-process
lock. The workspace remains simulation-only.

## Rehearse once

1. Set X/Y points to distinct values, close normally and reopen. Confirm both values.
2. Start a sufficiently long synthetic map (e.g. 30x31, integration .02 s).
3. Switch to Spectrum and try Acquire. Confirm Workspace busy identifies Intensity map
   and no spectrum worker starts.
4. Stop all, wait for Ready, then acquire a spectrum. Confirm it succeeds and releases.
5. Repeat map/spectrum after cleanup. Existing saved outputs must remain separate.
6. Close during acquisition, wait for cleanup, close again. No lease should remain.

## Focused validation

```powershell
uv run --no-sync ruff check --fix src/labtools/gui/workspace.py src/labtools/gui/workspace_panels.py src/labtools/simulation/ownership.py tests/test_workspace_ownership.py
uv run --no-sync pytest -q -ra tests/test_workspace_ownership.py tests/test_simulation_workspace.py
```

Sandbox: 22 passed, 2 skipped in 20.19s. Passing tests use the actual existing session,
actual adapter method bodies against fake worker bases, reservation conflicts,
startup refusal/failure, cancellation/cleanup ownership and release. The two skips are
actual Qt integration tests because PyQt6 is absent; they are not GUI acceptance.
The new Qt test also closes/reopens with isolated temporary settings to verify X/Y
memory, then exercises conflict rejection, Stop all and reuse after cleanup. Ruff is
unavailable in the sandbox; local lint and Qt execution remain required. No full suite,
hardware, packaging, ID900 or anneal work is performed.

The next integration boundary is explicit native resource configuration and service
injection, not enabling real controls. Preserve the existing worker affinity and use
existing session mechanisms; do not turn logical leases into claimed physical safety.
Historical test/package evidence stays linked to its original source revisions.
