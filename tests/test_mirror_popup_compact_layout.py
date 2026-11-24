"""Compact manual mirror action placement, with existing lifecycle unchanged."""
from PyQt6.QtWidgets import QFrame

pytest_plugins = ["test_experiment_panels", "test_experiment_workflows"]


def test_mirror_actions_beside_voltage_fields(window):
    app, widget, workspace = window
    popup = widget.mirror_window
    widget.mirror_button.click()
    app.processEvents()
    assert widget.mirror_button.text() == "Mirror"
    assert popup.move_actions.indexOf(popup.start_button) == 0
    assert popup.move_actions.indexOf(popup.stop_button) == 1
    frame = popup.x.parentWidget()
    while frame is not None and not isinstance(frame, QFrame):
        frame = frame.parentWidget()
    assert frame is not None
    assert frame.isAncestorOf(popup.start_button)
    assert frame.isAncestorOf(popup.stop_button)
    assert not frame.isAncestorOf(popup.home_button)
    assert popup.start_button.mapTo(popup, popup.start_button.rect().topLeft()).x() > popup.x.mapTo(popup, popup.x.rect().topRight()).x()
    assert not hasattr(workspace, "_mirror_last_commanded")
    popup.close()
