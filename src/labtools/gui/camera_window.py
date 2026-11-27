"""Independent modeless camera preview; raw dark subtraction and bounded rendering."""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event

import numpy as np
from PyQt6.QtCore import (
    QObject,
    QPointF,
    QRectF,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QFont, QImage, QImageReader, QPainter
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from labtools.io.camera_dark import MAX_BYTES, load_numeric_dark, save_dark_archive
from labtools.processing.camera_preview import LatestPreview, PreviewProcessor
from labtools.runtime.camera_stream import (
    CameraTargets,
    native_camera_factory,
    pump_camera,
)


class ImageSurface(QWidget):
    """Paint QImage directly; no per-frame QPixmap creation or pre-scaled copy."""

    view_changed = pyqtSignal()
    MAX_ZOOM = 8.0
    ZOOM_STEP = 1.25

    def __init__(self):
        super().__init__()
        self.setMinimumSize(240, 180)
        self._pixels = None
        self._image = QImage()
        self.zoom = 1.0
        self._centre = QPointF(.5, .5)
        self._pan_at = self._pan_button = None
        self.setToolTip("Wheel to zoom at the pointer; drag to pan. Middle drag also works in annotation mode.")

    def set_pixels(self, pixels):
        first_frame = self._image.isNull()
        self._pixels = pixels  # Keep the immutable contiguous numpy owner alive.
        height, width = pixels.shape[:2]
        fmt = QImage.Format.Format_Grayscale8 if pixels.ndim == 2 else QImage.Format.Format_BGR888
        self._image = QImage(pixels.data, width, height, pixels.strides[0], fmt)
        if first_frame:
            self.view_changed.emit()
        self.update()

    @property
    def has_image(self):
        return not self._image.isNull()

    def _target_rect(self, width, height):
        if min(width, height, self.width(), self.height()) <= 0:
            return QRectF()
        scale = self.zoom * min(self.width() / width, self.height() / height)
        w, h = width * scale, height * scale
        x = self.width() / 2 - self._centre.x() * w
        y = self.height() / 2 - self._centre.y() * h
        x = (self.width() - w) / 2 if w <= self.width() else min(0., max(self.width() - w, x))
        y = (self.height() - h) / 2 if h <= self.height() else min(0., max(self.height() - h, y))
        return QRectF(x, y, w, h)

    def target_rect(self):
        return self._target_rect(self._image.width(), self._image.height())

    def set_zoom(self, factor, anchor=None):
        if not self.has_image:
            return
        factor = min(self.MAX_ZOOM, max(1.0, factor))
        if factor == self.zoom:
            return
        before = self.target_rect()
        if before.isEmpty():
            return
        if anchor is None or not before.contains(anchor):
            anchor = QPointF(self.width() / 2, self.height() / 2)
        u = (anchor.x() - before.x()) / before.width()
        v = (anchor.y() - before.y()) / before.height()
        ratio = factor / self.zoom
        self.zoom = factor
        self._centre = QPointF(
            u + (self.width() / 2 - anchor.x()) / (before.width() * ratio),
            v + (self.height() / 2 - anchor.y()) / (before.height() * ratio),
        )
        self._commit_view()

    def _commit_view(self):
        rect = self.target_rect()
        if not rect.isEmpty():
            self._centre = QPointF((self.width() / 2 - rect.x()) / rect.width(),
                                   (self.height() / 2 - rect.y()) / rect.height())
        self.view_changed.emit()
        self.update()

    def reset_zoom(self):
        self.zoom = 1.0
        self._centre = QPointF(.5, .5)
        self._stop_pan()
        self.view_changed.emit()
        self.update()

    def clear_image(self):
        self._image = QImage()
        self._pixels = None
        self.reset_zoom()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120 or event.pixelDelta().y() / 120
        if self.has_image and steps and self.target_rect().contains(event.position()):
            self.set_zoom(self.zoom * self.ZOOM_STEP ** max(-8., min(8., steps)), event.position())
            event.accept()
            return
        event.ignore()

    def mousePressEvent(self, event):
        if (self.has_image and self.zoom > 1 and self._pan_at is None and self.target_rect().contains(event.position())
                and event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton)):
            self._pan_at, self._pan_button = event.position(), event.button()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_at is not None:
            rect = self.target_rect()
            if not rect.isEmpty():
                delta = event.position() - self._pan_at
                self._centre = QPointF((self.width() / 2 - rect.x() - delta.x()) / rect.width(),
                                       (self.height() / 2 - rect.y() - delta.y()) / rect.height())
                self._pan_at = event.position()
                self._commit_view()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _stop_pan(self):
        self._pan_at = self._pan_button = None
        self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if event.button() == self._pan_button:
            self._stop_pan()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._image.isNull():
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Camera stopped; press Start camera")
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(self.target_rect(), self._image)


class PreviewWorker(QObject):
    connected = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, *, targets, processor, mailbox, stop, factory):
        super().__init__()
        self.options = {"targets": targets, "processor": processor, "mailbox": mailbox,
                        "stop": stop, "factory": factory, "connected": self.connected.emit}

    @pyqtSlot()
    def run(self):
        try:
            pump_camera(**self.options)
        except Exception as error:  # noqa: BLE001 - preserve native errors at worker boundary
            self.failed.emit(str(error))
        finally:
            self.options["processor"].cancel_capture()
            self.finished.emit()


def load_image_dark(path):
    """PNG/JPEG via Qt, preserving supported grayscale depth; numeric files elsewhere."""
    if Path(path).suffix.lower() in {".npz", ".npy", ".tif", ".tiff"}:
        return load_numeric_dark(path)
    if Path(path).suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
        raise ValueError("Unsupported dark image format")
    if Path(path).stat().st_size > MAX_BYTES:
        raise ValueError("Dark image exceeds 256 MiB")
    reader = QImageReader(str(path))
    reader.setAutoTransform(False)  # Do not rotate/mirror relative to camera pixels.
    size = reader.size()
    if not size.isValid() or size.width() * size.height() * 8 > MAX_BYTES:
        raise ValueError("Invalid or oversized image")
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString())
    if image.format() == QImage.Format.Format_Grayscale16:
        channels, dtype = 1, np.uint16
    elif image.format() in (QImage.Format.Format_Grayscale8, QImage.Format.Format_Mono, QImage.Format.Format_MonoLSB) or (
        image.format() == QImage.Format.Format_Indexed8 and image.isGrayscale()
    ):
        image = image.convertToFormat(QImage.Format.Format_Grayscale8)
        channels, dtype = 1, np.uint8
    else:
        if image.depth() > 32:
            raise ValueError("Use raw TIFF/NPY for high-bit-depth colour darks")
        image = image.convertToFormat(QImage.Format.Format_BGR888)
        channels, dtype = 3, np.uint8
    pointer = image.constBits()
    pointer.setsize(image.sizeInBytes())
    rows = np.frombuffer(pointer, dtype=dtype).reshape(image.height(), image.bytesPerLine() // np.dtype(dtype).itemsize)
    data = rows[:, :image.width() * channels].copy()
    if channels == 1:
        data = data.reshape(image.height(), image.width())
    else:
        data = data.reshape(image.height(), image.width(), channels)
    return data, None


class CameraWindow(QDialog):
    """One independent camera handle, owned by its worker until thread-finished.

    Camera-only Start is available on explicit user request; no laser/shutter/stage
    actions or experiment execution gates are changed. No automatic connection.
    """

    surface_type = ImageSurface

    def __init__(self, parent=None, *, reserve=None, factory=native_camera_factory):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Live camera - independent preview")
        self.setModal(False)
        self.resize(1000, 760)
        self._reserve, self._factory = reserve, factory
        self._lease = None
        self._thread = self._worker = None
        self._close_pending = False
        self._error = None
        self._stop = Event()
        self.targets = CameraTargets()
        self.processor = PreviewProcessor()
        self.mailbox = LatestPreview()
        self._frames = 0
        self._stats_at = time.monotonic()
        self._last_sequence = 0
        self._last_packet = None
        self._last_arrival = 0.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)
        self.source_layout = QHBoxLayout()
        self.source_layout.setSpacing(8)
        layout.addLayout(self.source_layout)
        self.source_notice_layout = QVBoxLayout()
        layout.addLayout(self.source_notice_layout)

        actions = QHBoxLayout()
        self.start_button = QPushButton("Start camera")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumSize(170, 34)
        self.stop_button = QPushButton("Stop camera")
        self.stop_button.setMinimumSize(170, 34)
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.request_stop)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.overlay_layout = QVBoxLayout()
        self.overlay_layout.setSpacing(6)
        layout.addLayout(self.overlay_layout)
        self.surface = self.surface_type()
        self.surface.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        zoom_controls = QHBoxLayout()
        zoom_controls.addWidget(QLabel("Preview zoom"))
        self.zoom_out = QPushButton("−")
        self.zoom_out.setAccessibleName("Zoom out")
        self.zoom_in = QPushButton("+")
        self.zoom_in.setAccessibleName("Zoom in")
        self.zoom_fit = QPushButton("Fit")
        self.zoom_fit.setToolTip("Reset zoom and show the whole frame")
        self.zoom_indicator = QLabel()
        self.zoom_out.clicked.connect(lambda: self.surface.set_zoom(self.surface.zoom / self.surface.ZOOM_STEP))
        self.zoom_in.clicked.connect(lambda: self.surface.set_zoom(self.surface.zoom * self.surface.ZOOM_STEP))
        self.zoom_fit.clicked.connect(self.surface.reset_zoom)
        for control in (self.zoom_out, self.zoom_in, self.zoom_fit, self.zoom_indicator):
            zoom_controls.addWidget(control)
        zoom_controls.addStretch(1)
        layout.addLayout(zoom_controls)
        self.surface.view_changed.connect(self._update_zoom_controls)
        self._update_zoom_controls()

        preview_body = QWidget()
        preview_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview = QHBoxLayout(preview_body)
        preview.setContentsMargins(0, 0, 0, 0)
        preview.setSpacing(6)
        preview.addWidget(self.surface, 1)
        self.settings_toggle = QToolButton()
        self.settings_toggle.setCheckable(True)
        self.settings_toggle.setChecked(True)
        self.settings_toggle.setFixedWidth(28)
        self.settings_toggle.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        preview.addWidget(self.settings_toggle)

        self.settings_panel = QFrame()
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setMaximumWidth(310)
        self.settings_scroll.setWidget(self.settings_panel)
        settings = QVBoxLayout(self.settings_panel)
        settings.setContentsMargins(10, 4, 10, 4)
        settings.setSpacing(8)
        heading_font = QFont(self.font())
        heading_font.setPointSize(max(self.font().pointSize() + 1, 10))
        heading_font.setWeight(QFont.Weight.DemiBold)
        heading = QLabel("Camera settings")
        heading.setFont(heading_font)
        settings.addWidget(heading)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.exposure_ms = QDoubleSpinBox()
        self.exposure_ms.setRange(.01, 10000)
        self.exposure_ms.setDecimals(3)
        self.exposure_ms.setValue(20)
        self.gain = QDoubleSpinBox()
        self.gain.setRange(1, 100)
        self.gain.setDecimals(2)
        self.gain.setValue(1)
        self.display_ms = QDoubleSpinBox()
        self.display_ms.setRange(16, 10000)
        self.display_ms.setDecimals(0)
        self.display_ms.setValue(33)
        self.white_level = QDoubleSpinBox()
        self.white_level.setRange(1, 65535)
        self.white_level.setDecimals(0)
        self.white_level.setValue(65535)
        self.white_level.valueChanged.connect(self.processor.set_white)
        form.addRow("Exposure (ms)", self.exposure_ms)
        form.addRow("Master gain", self.gain)
        form.addRow("Display refresh (ms)", self.display_ms)
        form.addRow("16-bit preview white level", self.white_level)
        settings.addLayout(form)
        dark_heading = QLabel("Dark correction")
        dark_heading.setFont(heading_font)
        settings.addWidget(dark_heading)
        self.capture_button = QPushButton("Capture dark")
        self.capture_button.setEnabled(False)
        self.load_button = QPushButton("Load dark image")
        self.save_dark_button = QPushButton("Save dark (.npz)")
        self.clear_button = QPushButton("Clear dark")
        self.subtract = QCheckBox("Subtract dark")
        for button in (self.capture_button, self.load_button, self.save_dark_button, self.clear_button):
            settings.addWidget(button)
        settings.addWidget(self.subtract)
        self.capture_button.clicked.connect(self.capture_dark)
        self.load_button.clicked.connect(self.load_dark)
        self.save_dark_button.clicked.connect(self.save_dark)
        self.clear_button.clicked.connect(self.clear_dark)
        self.subtract.toggled.connect(self.processor.enable)
        self.dark_status = QLabel("No dark image; subtraction off")
        self.dark_status.setWordWrap(True)
        settings.addWidget(self.dark_status)
        settings.addStretch(1)
        preview.addWidget(self.settings_scroll)
        layout.addWidget(preview_body, 1)
        self.settings_toggle.toggled.connect(self._set_settings_visible)
        self._set_settings_visible(True)

        self.status = QLabel("Camera: NOT PROBED")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout.addWidget(self.status)
        self.metrics = QLabel("Preview: fixed 8/16-bit scale; no per-frame autoscaling")
        self.metrics.setWordWrap(True)
        self.metrics.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout.addWidget(self.metrics)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.draw_latest)
        self.exposure_ms.valueChanged.connect(self.update_targets)
        self.gain.valueChanged.connect(self.update_targets)
        self.display_ms.valueChanged.connect(self.update_interval)
        self._connected_ok = False
        from labtools.gui.operator_ui import (
            fit_initial_window,
            protect_parameter_wheels,
        )

        fit_initial_window(self, preferred=(1000, 760))
        protect_parameter_wheels(self)

    def _update_zoom_controls(self):
        zoom = self.surface.zoom
        ready = self.surface.has_image
        self.zoom_indicator.setText("Fit (1×)" if zoom == 1 else f"{zoom:.2f}× fit")
        self.zoom_out.setEnabled(ready and zoom > 1)
        self.zoom_fit.setEnabled(ready and zoom > 1)
        self.zoom_in.setEnabled(ready and zoom < self.surface.MAX_ZOOM)

    def _set_settings_visible(self, visible):
        self.settings_scroll.setVisible(visible)
        self.settings_toggle.setArrowType(
            Qt.ArrowType.RightArrow if visible else Qt.ArrowType.LeftArrow
        )
        label = "Hide camera settings" if visible else "Show camera settings"
        self.settings_toggle.setToolTip(label)
        self.settings_toggle.setAccessibleName(label)

    @property
    def busy(self):
        return self._thread is not None

    def update_targets(self):
        self.targets.update(self.exposure_ms.value() / 1000, self.gain.value())
        if self.subtract.isChecked():
            self.dark_status.setText("Settings changed; dark compatibility will be rechecked on next frame")

    def update_interval(self):
        self.timer.setInterval(int(self.display_ms.value()))

    def start(self):
        if self.busy:
            return
        self._error = None
        self._close_pending = False
        self._connected_ok = False
        try:
            if self._reserve is not None:
                self._lease = self._reserve()
            self.update_targets()
            self._stop.clear()
            self.mailbox.take()
            self._last_packet = None
            self._frames, self._stats_at = 0, time.monotonic()
            thread = QThread(self)
            worker = PreviewWorker(targets=self.targets, processor=self.processor, mailbox=self.mailbox,
                                   stop=self._stop, factory=self._factory)
            self._thread, self._worker = thread, worker
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.connected.connect(self.connected)
            worker.failed.connect(self.failed)
            worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(self._worker_finished)
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status.setText("Connecting camera on preview worker...")
            self.timer.start(int(self.display_ms.value()))
            thread.start()
        except Exception as error:  # noqa: BLE001 - startup must release a reservation
            if self._thread is None or not self._thread.isRunning():
                self._worker_finished()
            self.failed(str(error))

    def connected(self, info):
        self._connected_ok = True
        # Do not overwrite a newer user request queued while connecting.
        self.status.setText(f"Connected: {info['device_info']} | exposure {info['exposure_s'] * 1000:.3f} ms | "
                            f"gain {info['applied_gain']:.2f} (max {info['maximum_gain']:.2f})")
        self.gain.setMaximum(max(1., min(100., float(info["maximum_gain"]))))
        self.capture_button.setEnabled(not self._stop.is_set())

    def failed(self, message):
        self._error = message
        self.status.setText("Camera error: " + message)

    def request_stop(self):
        if not self.busy:
            return
        self._stop.set()
        self.stop_button.setEnabled(False)
        self.capture_button.setEnabled(False)
        self.status.setText("Stopping camera; waiting for frame/SDK cleanup...")

    def _worker_finished(self):
        self.timer.stop()
        thread = self._thread
        self._thread = self._worker = None
        self.processor.cancel_capture()
        if thread is not None:
            thread.deleteLater()
        if self._lease is not None:
            self._lease.release()
            self._lease = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.capture_button.setEnabled(False)
        self._connected_ok = False
        self.status.setText("Camera error: " + self._error if self._error else "Camera stopped; last preview retained")
        if self._close_pending:
            self._close_pending = False
            self.close()

    def draw_latest(self):
        self.processor.set_size(self.surface.width(), self.surface.height())
        packet = self.mailbox.take()
        now = time.monotonic()
        if packet is not None:
            self._last_packet = packet
            self._last_arrival = now
            self._last_sequence = packet.sequence
            self.surface.set_pixels(packet.pixels)
            self.dark_status.setText(packet.dark_status)
            self._frames += 1
        if now - self._stats_at >= .5:
            if self._last_packet is not None:
                age = max(0., now - self._last_packet.acquired_at) * 1000
                self.metrics.setText(f"Display {self._frames / (now - self._stats_at):.1f} fps | "
                                     f"post-read age {age:.0f} ms | raw {self._last_packet.raw_shape} "
                                     f"{self._last_packet.raw_dtype} | replaced previews {self.mailbox.replaced} | "
                                     f"uint8 0..255 / uint16 white {self.white_level.value():.0f}")
            self._frames, self._stats_at = 0, now

    def capture_dark(self):
        if not self.busy or not self._connected_ok or self._stop.is_set():
            self.dark_status.setText("Start the camera before capturing a dark")
            return
        self.processor.capture_dark()
        self.dark_status.setText("Capturing next raw frame: keep illumination blocked. No shutter action is performed.")

    def load_dark(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load raw dark image", "",
                                             "Dark images (*.npz *.npy *.tif *.tiff *.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        try:
            frame, context = load_image_dark(path)
            self.processor.load_dark(frame, context=context,
                                     origin="loaded metadata dark" if context else "loaded image; exposure/gain/orientation unverified")
            self.dark_status.setText("Dark loaded; raw shape/dtype/settings will be checked on the next frame. "
                                    "Use matching exposure, gain and orientation; lossy images are not calibrated darks.")
        except Exception as error:  # noqa: BLE001 - file decoding errors are user-facing
            QMessageBox.warning(self, "Dark image not loaded", str(error))

    def save_dark(self):
        try:
            frame, context, origin = self.processor.dark_snapshot()
            if "unverified" in origin:
                context = None
            path, _ = QFileDialog.getSaveFileName(self, "Save raw dark", "camera-dark.npz", "Dark archive (*.npz)")
            if path:
                if not path.lower().endswith(".npz"):
                    path += ".npz"
                save_dark_archive(path, frame, context)
        except Exception as error:  # noqa: BLE001
            QMessageBox.warning(self, "Dark image not saved", str(error))

    def clear_dark(self):
        self.subtract.setChecked(False)
        self.processor.clear_dark()
        self.dark_status.setText("Dark cleared; subtraction off")

    def closeEvent(self, event):
        if self.busy:
            self._close_pending = True
            self.request_stop()
            event.ignore()
            return
        # Hide/reopen the same window; no auto-start and no hardware state restored.
        event.accept()
