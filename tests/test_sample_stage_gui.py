"""Unified sample-stage popup and focus controls; simulation only."""

from test_experiment_panels import spin

pytest_plugins = ["test_experiment_panels"]


def connect_stage(app, widget):
    popup = widget.stage_window
    popup.command("connect")
    spin(app, lambda: not popup.busy)
    assert popup.service.connected, popup.status.text()
    return popup


def test_stage_header_no_connection_on_open(window):
    app, widget, _workspace = window
    popup = widget.stage_window
    assert widget.stage_button.text() == "Stage"
    widget.stage_button.click()
    app.processEvents()
    assert popup.isVisible() and not popup.service.connected
    assert popup.styleSheet() == widget.styleSheet()
    popup.close()
    assert not popup.service.connected


def test_stage_axis_ramp_and_step(window):
    app, widget, _workspace = window
    popup = connect_stage(app, widget)
    popup.command("ramp", 1, 30)
    spin(app, lambda: not popup.busy)
    assert popup.service.device.offset[1] == 30
    popup.command("step", 1, 1)
    spin(app, lambda: not popup.busy)
    assert popup.service.device.offset[1] == 0


def test_focus_stack_runs_browses_and_retains(window):
    app, widget, _workspace = window
    popup = connect_stage(app, widget)
    panel = widget.pages["Intensity map"]
    focus = panel.focus_controls
    panel.save_results.setChecked(False)
    focus.enabled.setChecked(True)
    focus.levels.setText("0, 20")
    focus.sweeps.setValue(2)
    focus.settle.setValue(0)
    panel.start_new()
    spin(app, lambda: not panel.map_controller.busy)
    assert focus.run is not None, panel.status.text()
    assert focus.run["status"] == "completed", focus.run
    assert len(focus.run["maps"]) == 4
    assert focus.browse.count() == 4
    focus.browse.setCurrentIndex(0)
    assert "DC 0 V" in panel.axes.get_title()
    assert panel.retained_run.get()["result"]["kind"] == "multi-z-intensity-map"
    assert not popup.service.busy


def test_manual_stage_excluded_by_map_reservation(window):
    app, widget, workspace = window
    popup = connect_stage(app, widget)
    lease = workspace._ownership.reserve("Intensity map")
    try:
        popup.command("step", 1, 1)
        assert not popup.busy
        assert popup.service.device.offset[1] == 0
    finally:
        lease.release()


def test_stage_settings_survive_display_roundtrip_without_motion(window):
    app, widget, _workspace = window
    focus = widget.pages["Intensity map"].focus_controls
    focus.levels.setText("0, 25, 50")
    focus.sweeps.setValue(2)
    data = widget.display_preferences()
    focus.levels.setText("0")
    focus.restore(data)
    assert focus.levels.text() == "0, 25, 50"
    assert not widget.stage_window.service.connected
    app.processEvents()
