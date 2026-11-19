# Map display backpressure

The map worker previously queued a Qt progress event for every acquired point.
Each event updated the full map, axes, colour scale and status. Fast producers
could leave the GUI draining stale plots instead of handling Stop or close.
This is a confirmed unbounded path, not a captured stack trace of the reported hang.

MapController now retains one latest immutable acquisition snapshot behind a lock.
A GUI-thread timer consumes it every 100 ms. The worker does not emit per-point
Qt progress events through this controller. Terminal handlers flush the latest
snapshot before finished/failed, then normal thread cleanup releases ownership.
Cancel still sets the worker's threading.Event directly and stops periodic display
updates. Final partial progress is retained. A new run starts with an empty slot.
Standalone MapWorker signal behaviour is retained for existing direct consumers.

Only intermediate display frames are coalesced. Acquisition, averaging, integration,
settling, per-point logging, checkpoint frequency, final arrays and native execution
gates are unchanged. Both standalone and workspace map windows use this controller.
This does not interrupt an in-flight hardware call or make arbitrary slow rendering
instantaneous. Large-map snapshot construction/checkpoint cost is not addressed.

## Validation

Run ruff check --fix on the changed Python paths and pytest on:
- tests/test_map_progress_backpressure.py
- tests/test_qt_controllers.py
- tests/test_intensity_map_simulation.py
- tests/test_simulated_operator_session.py
- tests/test_simulated_operator_window.py

The new QtCore tests cover a 20,000-update burst, final progress before success and
failure, GUI-thread delivery, timer-driven cancellation with a slow display consumer,
heartbeat activity, and restart. They are not full-window/camera acceptance.

## Required development-PC rehearsal

Use the explicit simulation workspace, with the simulated camera preview running.
Use the same map dimensions and integration/settling settings that previously hung.
Click Stop once during the map; confirm controls remain responsive, partial map is
retained, cleanup finishes and a second map can start. With saved output enabled,
confirm the partial checkpoint can resume. During another map, close the workspace;
confirm cooperative stopping and deferred close rather than a destroyed live worker.
Repeat with integration 0.02 s. Record observed results, not inferred acceptance.

No real instruments or local instrument configuration are changed by this batch.
