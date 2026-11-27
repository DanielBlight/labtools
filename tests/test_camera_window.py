"""Actual popup/render/worker cleanup tests; absent Qt is not acceptance."""

import time
from threading import get_ident

import numpy as np
import pytest


def qt(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as error:
        pytest.skip(f"Camera Qt acceptance unavailable: {error}")
    return QApplication.instance() or QApplication([])


def test_popup_modeless_live_dark_close_cleanup_and_reopen(monkeypatch):
    app = qt(monkeypatch)
    from labtools.gui.camera_window import CameraWindow

    calls, threads = [], []
    caller = get_ident()

    class Lease:
        def release(self):
            calls.append("release")

    class Camera:
        def __init__(self, **kwargs):
            self.exposure = kwargs["exposure_s"]
            self.gain = 1
            threads.append(get_ident())

        def __enter__(self):
            calls.append("enter")
            return self

        def __exit__(self, *args):
            calls.append("close")
            threads.append(get_ident())

        def get_max_gains(self):
            return (4,)

        def set_master_gain(self, gain):
            self.gain = gain
            return gain

        def set_exposure(self, exposure):
            self.exposure = exposure
            return exposure

        def get_exposure(self):
            return self.exposure

        def get_device_info(self):
            return "test-only camera"

        def start_live(self, **kwargs):
            calls.append("start")

        def read_latest(self, **kwargs):
            time.sleep(.005)
            threads.append(get_ident())
            return np.full((48, 64, 3), 25, np.uint8)

    window = CameraWindow(reserve=Lease, factory=Camera)

    def wait(predicate):
        end = time.monotonic() + 5
        while not predicate():
            app.processEvents()
            time.sleep(.005)
            assert time.monotonic() < end, "Camera worker cleanup timed out"
        app.processEvents()

    try:
        window.show()
        app.processEvents()
        assert not window.isModal() and not window.busy and calls == []
        for _ in range(2):
            window.start_button.click()
            wait(lambda: window._connected_ok and window._last_packet is not None)
            assert window.busy
            window.capture_button.click()
            window.subtract.setChecked(True)
            wait(lambda: window._last_packet.corrected)
            assert not window._last_packet.pixels.any()
            window.close()  # Must request stop and defer hide until handle closed.
            wait(lambda: not window.busy)
            assert calls[-2:] == ["close", "release"]
            assert not window.isVisible()
            window.show()
            app.processEvents()
            assert not window.busy
        assert caller not in threads
        window.surface.set_pixels(np.array([[[255, 0, 0]]], dtype=np.uint8))
        colour = window.surface._image.pixelColor(0, 0)
        assert (colour.red(), colour.green(), colour.blue()) == (0, 0, 255)
    finally:
        window.request_stop()
        wait(lambda: not window.busy)
        window.close()


def test_png_raw_depth_and_colour_loading(tmp_path, monkeypatch):
    app = qt(monkeypatch)
    from PyQt6.QtGui import QColor, QImage

    from labtools.gui.camera_window import load_image_dark

    image = QImage(3, 2, QImage.Format.Format_RGB888)
    image.fill(QColor(10, 20, 30))
    path = tmp_path / "colour.png"
    assert image.save(str(path))
    frame, context = load_image_dark(path)
    assert frame.shape == (2, 3, 3) and context is None
    assert frame[0, 0].tolist() == [30, 20, 10]
    mono = QImage(3, 2, QImage.Format.Format_Grayscale16)
    mono.fill(0)
    assert mono.save(str(tmp_path / "mono.png"))
    frame, _ = load_image_dark(tmp_path / "mono.png")
    assert frame.dtype == np.uint16 and frame.shape == (2, 3)
    app.processEvents()


def test_failed_camera_open_releases_lease_and_allows_retry(monkeypatch):
    app = qt(monkeypatch)
    from labtools.gui.camera_window import CameraWindow

    released = []

    class Lease:
        def release(self):
            released.append(True)

    def fail(**kwargs):
        raise RuntimeError("test-only unavailable camera")

    window = CameraWindow(reserve=Lease, factory=fail)
    try:
        for _ in range(2):
            window.start()
            end = time.monotonic() + 5
            while window.busy:
                app.processEvents()
                time.sleep(.005)
                assert time.monotonic() < end
            assert "unavailable" in window.status.text()
        assert len(released) == 2
    finally:
        window.close()


def test_settings_toggle_preserves_outer_geometry_and_zoom(monkeypatch):
    app = qt(monkeypatch)
    from labtools.gui.camera_window import CameraWindow

    window = CameraWindow()
    try:
        window.show()
        app.processEvents()
        window.surface.set_pixels(np.zeros((300, 400), dtype=np.uint8))
        window.surface.set_zoom(2.)
        original = window.size()
        preview_height = window.surface.height()
        window.settings_toggle.setChecked(False)
        app.processEvents()
        assert window.size() == original
        assert not window.settings_scroll.isVisible()
        assert window.surface.height() >= preview_height - 2
        assert window.surface.zoom == 2.
        window.settings_toggle.setChecked(True)
        app.processEvents()
        assert window.size() == original
        assert window.settings_scroll.isVisible()
        assert window.surface.zoom == 2.
    finally:
        window.close()
