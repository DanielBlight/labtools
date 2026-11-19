"""Actual overlay UI and synthetic feed tests. Qt skips never imply acceptance."""

import builtins
import time

import numpy as np
import pytest


def test_simulation_overlay_drag_undo_dark_and_no_hardware(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication
    except ImportError as error:
        pytest.skip(f"Camera overlay Qt acceptance unavailable: {error}")
    from labtools.gui.camera_tools import CameraWindow

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "pylablib", "u6", "serial", "pyvisa")):
            raise AssertionError("Simulated UI attempted native import: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    app = QApplication.instance() or QApplication([])

    def forbidden(*args, **kwargs):
        pytest.fail("Simulation attempted real reservation or camera factory")

    window = CameraWindow(reserve=forbidden, factory=forbidden)

    def wait(predicate):
        end = time.monotonic() + 8
        while not predicate():
            app.processEvents()
            time.sleep(.005)
            assert time.monotonic() < end, "Synthetic UI did not finish"
        app.processEvents()

    try:
        window.show()
        app.processEvents()
        assert window.source.currentData() == "simulation" and not window.busy
        window.start_button.click()
        wait(lambda: window._last_packet is not None and window.surface.annotations.geometry is not None)
        assert "SIMULATED" in window.status.text() and not window.source.isEnabled()
        window.crosshair.setChecked(True)
        window.rings.setChecked(True)
        window.spacing.setValue(40)
        window.ring_count.setValue(4)
        assert window.surface.annotations.ring_spacing == 40
        window.draw_mode.setChecked(True)
        window.label_text.setText("Test spot")
        rect = window.surface.target_rect()
        centre = QPoint(int(rect.center().x()), int(rect.center().y()))
        edge = QPoint(centre.x() + 40, centre.y())
        QTest.mousePress(window.surface, Qt.MouseButton.LeftButton, pos=centre)
        QTest.mouseMove(window.surface, edge)
        QTest.mouseRelease(window.surface, Qt.MouseButton.LeftButton, pos=edge)
        assert len(window.surface.annotations.circles) == 1
        circle = window.surface.annotations.circles[0]
        assert circle.label == "Test spot" and circle.radius > 1
        pixels = window._last_packet.pixels.copy()
        window.surface.grab()  # Execute the actual overlay paint path.
        assert np.array_equal(pixels, window._last_packet.pixels)
        window.resize(1200, 900)
        app.processEvents()
        assert window.surface.annotations.circles[0] == circle
        window.undo_button.click()
        assert not window.surface.annotations.circles
        window.sim_dark.setChecked(True)
        sequence = window._last_packet.sequence
        wait(lambda: window._last_packet.sequence >= sequence + 3)
        window.capture_button.click()
        window.subtract.setChecked(True)
        wait(lambda: window._last_packet.corrected)
        assert window._last_packet.pixels.mean() < 3
        window.sim_dark.setChecked(False)
        wait(lambda: window._last_packet.corrected and window._last_packet.pixels.max() > 80)
        window.close()
        wait(lambda: not window.busy)
        assert not window.isVisible()
        window.show()
        app.processEvents()
        assert not window.busy
        window.source.setCurrentIndex(1)
        assert not window.sim_dark.isEnabled()
        assert window._last_packet is None and not window.subtract.isChecked()
        assert "REAL" in window.windowTitle()
    finally:
        window.request_stop()
        wait(lambda: not window.busy)
        window.close()
