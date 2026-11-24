"""Presentation-only details, header parity and compact mirror actions."""

import pytest
from PyQt6.QtWidgets import QLabel
from test_experiment_panels import spin

pytest_plugins = ["test_experiment_panels"]


@pytest.mark.parametrize('name', ['Hyperspectral', 'Sequences'])
def test_details_collapsed_and_expand_without_losing_log(window, name):
    app, widget, _ = window
    panel = widget.pages[name]
    widget.tabs.setCurrentWidget(panel)
    app.processEvents()
    assert panel.details_button.isVisible()
    assert not panel.log.isVisible()
    before = panel.canvas.height()
    panel.log.appendPlainText('Retained output path and diagnostic')
    panel.details_button.click()
    app.processEvents()
    assert panel.log.isVisible()
    assert 'diagnostic' in panel.log.toPlainText()
    assert panel.canvas.height() < before
    panel.details_button.click()
    app.processEvents()
    assert not panel.log.isVisible()
    assert panel.canvas.height() >= before - 1
    assert 'diagnostic' in panel.log.toPlainText()


def test_header_camera_mirror_exact_dimensions_and_style(window):
    app, widget, _ = window
    app.processEvents()
    camera, mirror = widget.camera_button, widget.mirror_button
    assert camera.size() == mirror.size()
    assert camera.font() == mirror.font()
    assert mirror.styleSheet().replace('#mirrorAction', '#cameraAction') == camera.styleSheet()
    assert '#16796f' in mirror.styleSheet()
    widget.resize(1100, 760)
    app.processEvents()
    assert camera.size() == mirror.size()


def test_mirror_compact_centered_actions_and_no_blank_log(window):
    app, widget, workspace = window
    popup = widget.mirror_window
    widget.mirror_button.click()
    app.processEvents()
    assert popup.isVisible() and not popup.log.isVisible()
    assert not popup.right.isVisible()
    texts = [label.text() for label in popup.findChildren(QLabel) if label.isVisible()]
    assert 'Commanded voltages, not readback.' in texts
    assert not any('Explicit movement only.' in text for text in texts)
    row = popup.move_row
    assert row.itemAt(0).spacerItem() is not None
    assert row.itemAt(row.count()-1).spacerItem() is not None
    assert popup.start_button.width() == popup.stop_button.width()
    start = popup.start_button.mapTo(popup, popup.start_button.rect().topLeft()).x()
    end = popup.stop_button.mapTo(popup, popup.stop_button.rect().topRight()).x()
    assert abs((start + end)/2 - popup.width()/2) <= 2
    assert popup.height() <= 360
    assert not hasattr(workspace, '_mirror_last_commanded')
    popup.x.setValue(.1)
    popup.y.setValue(-.2)
    popup.start_button.click()
    spin(app, lambda: not popup.busy)
    assert workspace._mirror_last_commanded == (.1, -.2)
    assert not popup.log.isVisible()
    assert 'Last commanded' in popup.status.text()
    popup.close()
    assert workspace._mirror_last_commanded == (.1, -.2)


def test_completed_cube_status_and_save_remain_without_details(window):
    app, widget, _ = window
    panel = widget.pages['Hyperspectral']
    widget.tabs.setCurrentWidget(panel)
    panel.save_output.setChecked(False)
    panel.start()
    spin(app, lambda: not panel.busy)
    assert panel.last_result.completed_points == 4
    assert panel.save_result_button.isEnabled()
    assert not panel.log.isVisible()
    assert 'Cube complete' in panel.status.text()
    panel.details_button.click()
    assert panel.log.isVisible()
