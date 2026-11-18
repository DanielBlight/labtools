# Unified simulation workspace: first integrated operator window

## Launch

```powershell
uv run --no-sync labtools simulate workspace
```

Optional initial output root:

```powershell
uv run --no-sync labtools simulate workspace --output "C:\Labtools Simulation"
```

One application/event loop contains Intensity map and Spectrum tabs. The existing
complete workflow windows are embedded as panels, not launched as separate processes.
Each panel keeps its controls, status, plot, acquisition worker and close behaviour.
Switching tabs does not recreate a panel or discard its result/dark/settings.

This first integrated window is simulation-only. There is no real-backend switch,
laser connection, device registry or shared native connection. Independent synthetic
workflows can run concurrently; that is not permission for concurrent real hardware.
Existing standalone launchers and the InstrumentSession implementation are unchanged.

## Shared controls

- Permanent simulation identification and one window title.
- Common initial output root, with separate Maps and Spectra folders. Individual panels
  can still choose their output folder; the header describes the initial root.
- Global activity indicator includes acquisition and worker teardown.
- Stop all active workflows calls each existing cooperative cancellation method.
- Closing during an operation requests Stop all and refuses close until cleanup ends.
  Wait for Ready, then close again. No active worker is forcibly terminated.

The 200 ms activity timer is presentation only. Close/Stop inspect live worker state
synchronously. It stops when the window closes. Stop all is not an emergency interlock.

## One useful rehearsal

1. Confirm two tabs in one SIMULATION ONLY window and disabled laser controls.
2. In Intensity map, complete the initial 5x5 grid. Its existing real-time simulation
   option is enabled to make progress and Stop observable. Inspect its saved output.
3. Switch to Spectrum, tick Save CSV/PNG, acquire raw, capture a reusable dark and
   subtract it as in the previous accepted spectroscopy rehearsal.
4. Switch back. The map result should still be present. Repeat without overwriting it.
5. Start a larger map, switch tabs, then use Stop all. Wait for cleanup and inspect
   the incomplete checkpoint. Resume through the existing map control.
6. Attempt to close during a map. The window should remain open while cancellation
   completes; close again when Ready. Reopen and confirm no orphan worker warnings.

Initial grid and spectrum range are deliberately 5x5 and 500-600 nm for this rehearsal;
this shell does not add new workspace persistence. Existing map preferences still save
through its original close handler. Spectrum remains toy-scene-v1; values are not
approved detector or optical-path settings.

## Validation and next boundary

```powershell
uv run --no-sync ruff check --fix src/labtools/cli.py src/labtools/gui/workspace.py src/labtools/simulation/workspace.py tests/test_simulation_workspace.py
uv run --no-sync pytest -q -ra tests/test_simulation_workspace.py
```

Sandbox results: 12 passed, 1 skipped in 12.19s. Passing tests exercise actual Qt-free
lifecycle helpers and CLI routing with fake Qt construction. The skipped test uses real
Qt, embedded existing panels, synthetic acquisition, tab switching, global activity,
close-during-map cancellation and idle close, with native imports forbidden. PyQt6 is
absent in the sandbox; this is not actual unified-window acceptance. Local execution
and visual rehearsal are required. Ruff is unavailable there. No full-suite rerun.

The accepted standalone spectroscopy GUI milestone is closed by user confirmation and
supplied raw/corrected outputs. Historical validation remains attached to its source
revisions. This new composition has separate validation; no hardware/packaging/anneal
or ID900 changes are made.

Next after successful rehearsal: integrate explicit shared operation ownership and
configuration at the workspace boundary before exposing real controls. Do not treat
these two tabs as shared native-device ownership. Use the existing session mechanisms
rather than inventing a second registry, and preserve native thread/async-loop affinity.
