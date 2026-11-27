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


def test_preview_zoom_wheel_pan_and_fit(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    from labtools.gui.camera_tools import CameraWindow

    app = QApplication.instance() or QApplication([])
    window = CameraWindow()
    try:
        window.show()
        window.surface.setFixedSize(400, 300)
        app.processEvents()
        surface = window.surface
        assert not window.zoom_in.isEnabled()
        pixels = np.zeros((300, 400), dtype=np.uint8)
        surface.set_geometry(pixels.shape)
        surface.set_pixels(pixels)
        fit = surface.target_rect()
        anchor = fit.center() + QPointF(20, 0)
        original_point = surface.point(anchor)
        wheel = QWheelEvent(anchor, surface.mapToGlobal(anchor), QPoint(), QPoint(0, 120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(surface, wheel)
        assert surface.zoom == pytest.approx(1.25)
        assert surface.point(anchor) == pytest.approx(original_point)
        assert window.zoom_fit.isEnabled()
        window.zoom_in.click()
        window.zoom_in.click()
        start = QPoint(surface.width() // 2, surface.height() // 2)
        before = surface.target_rect()
        window.draw_mode.setChecked(True)
        QTest.mousePress(surface, Qt.MouseButton.MiddleButton, pos=start)
        QTest.mouseMove(surface, start + QPoint(40, 0))
        QTest.mouseRelease(surface, Qt.MouseButton.MiddleButton, pos=start + QPoint(40, 0))
        assert surface.target_rect().x() > before.x()
        assert not surface.annotations.circles
        zoomed = surface.target_rect()
        surface.set_pixels(pixels.copy())
        assert surface.target_rect() == zoomed
        assert surface.grab().size() == surface.size()
        for _ in range(24):
            window.zoom_in.click()
        assert surface.zoom == surface.MAX_ZOOM and not window.zoom_in.isEnabled()
        window.zoom_fit.click()
        assert surface.target_rect() == fit and surface.zoom == 1
        window.zoom_in.click()
        window.source.setCurrentIndex(1)
        assert surface.zoom == 1 and not window.zoom_in.isEnabled()
    finally:
        window.close()
