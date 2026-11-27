"""Display-only camera overlays and explicit synthetic feed for development.

Extends the existing modeless preview without changing camera acquisition, dark
arithmetic, experiment gates or native wrapper imports.
"""

from __future__ import annotations

import argparse
import math
import sys

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
)

from labtools.gui.camera_window import CameraWindow as BaseCameraWindow
from labtools.gui.camera_window import ImageSurface
from labtools.processing.camera_annotations import CameraAnnotations, image_point
from labtools.simulation.camera import SimulatedCamera, SimulatedIllumination


class AnnotationSurface(ImageSurface):
    changed = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.annotations = CameraAnnotations()
        self.draw_circles = False
        self.annotation_label = ""
        self.synthetic = True
        self._drag = None
        self._edge = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def target_rect(self):
        geometry = self.annotations.geometry
        if geometry is None:
            return QRectF()
        return self._target_rect(*geometry)

    def set_geometry(self, raw_shape):
        if self.annotations.set_geometry(int(raw_shape[1]), int(raw_shape[0])):
            self.cancel_drag()
            self.message.emit("Image dimensions changed; annotations cleared")
        self.changed.emit()

    def point(self, position):
        rect = self.target_rect()
        return image_point(position.x(), position.y(), (rect.x(), rect.y(), rect.width(), rect.height()),
                           self.annotations.geometry)

    def cancel_drag(self):
        self._drag = self._edge = None
        self.update()

    def undo(self):
        self.cancel_drag()
        self.annotations.undo()
        self.changed.emit()
        self.update()

    def clear(self):
        self.cancel_drag()
        self.annotations.clear()
        self.changed.emit()
        self.update()

    def mousePressEvent(self, event):
        if self.draw_circles and event.button() == Qt.MouseButton.LeftButton and not self._image.isNull():
            point = self.point(event.position())
            if point is not None:
                self.setFocus()
                self._drag = self._edge = point
                self.update()
                event.accept()
                return
            event.ignore()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_at is None and self._drag is not None:
            self._edge = self.point(event.position())
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag is not None:
            point = self.point(event.position())
            try:
                if point is None:
                    raise ValueError("Circle cancelled: release inside the image")
                self.annotations.add(self._drag, point, self.annotation_label)
                self.message.emit("Circle added; Undo removes the last annotation")
            except ValueError as error:
                self.message.emit(str(error))
            self.cancel_drag()
            self.changed.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._drag is not None:
            self.cancel_drag()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._image.isNull() or self.annotations.geometry is None:
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Select a source and press Start camera")
            return
        rect = self.target_rect()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(rect, self._image)
        painter.save()
        painter.setClipRect(rect)
        width, height = self.annotations.geometry
        sx, sy = rect.width() / width, rect.height() / height

        def point(x, y):
            return QPointF(rect.x() + x * sx, rect.y() + y * sy)

        def circle(x, y, radius, colour):
            painter.setPen(QPen(QColor(colour), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(point(x, y), radius * sx, radius * sy)

        model = self.annotations
        if model.crosshair:
            painter.setPen(QPen(QColor("#00ff88"), 1.))
            painter.drawLine(point(0, height / 2), point(width, height / 2))
            painter.drawLine(point(width / 2, 0), point(width / 2, height))
        if model.rings:
            for index in range(1, model.ring_count + 1):
                circle(width / 2, height / 2, index * model.ring_spacing, "#00ff88")
        for annotation in model.circles:
            circle(annotation.x, annotation.y, annotation.radius, "#ffcf40")
            text = f"{annotation.label} | r={annotation.radius:.1f} px"
            anchor = point(annotation.x + annotation.radius, annotation.y)
            metrics = painter.fontMetrics()
            x = min(max(rect.left() + 3, anchor.x() + 5), max(rect.left() + 3, rect.right() - metrics.horizontalAdvance(text) - 5))
            y = min(max(rect.top() + metrics.ascent() + 3, anchor.y()), rect.bottom() - 3)
            bounds = QRectF(x - 2, y - metrics.ascent() - 1, metrics.horizontalAdvance(text) + 4, metrics.height() + 2)
            painter.fillRect(bounds, QColor(0, 0, 0, 180))
            painter.setPen(QColor("#ffcf40"))
            painter.drawText(QPointF(x, y), text)
        if self._drag is not None and self._edge is not None:
            radius = math.hypot(self._edge[0] - self._drag[0], self._edge[1] - self._drag[1])
            circle(*self._drag, radius, "#ffffff")
        if self.synthetic:
            visible = rect.intersected(QRectF(self.rect()))
            painter.fillRect(QRectF(visible.x(), visible.y(), 270, 25), QColor(0, 0, 0, 200))
            painter.setPen(QColor("#ffcf40"))
            painter.drawText(QPointF(visible.x() + 7, visible.y() + 18), "SIMULATED - NOT CAMERA DATA")
        painter.restore()


class CameraWindow(BaseCameraWindow):
    surface_type = AnnotationSurface

    def __init__(self, parent=None, *, reserve=None, **kwargs):
        super().__init__(parent, reserve=reserve, **kwargs)
        self._real_factory = self._factory
        self._real_reserve = reserve
        self._illumination = SimulatedIllumination()
        self._source_mode = "simulation"
        sources = QHBoxLayout()
        sources.addWidget(QLabel("Preview source"))
        self.source = QComboBox()
        self.source.addItem("Simulated camera (no hardware)", "simulation")
        self.source.addItem("Real UC480 camera (explicit Start)", "real")
        sources.addWidget(self.source)
        self.sim_dark = QCheckBox("Simulated dark scene")
        self.sim_dark.toggled.connect(self._illumination.set_dark)
        sources.addWidget(self.sim_dark)
        self.source_layout.addLayout(sources)
        self.source_notice = QLabel("SIMULATION SELECTED: generated images only; no hardware connection")
        self.source_notice.setWordWrap(True)
        self.source_notice_layout.addWidget(self.source_notice)
        controls = QHBoxLayout()
        self.crosshair = QCheckBox("Crosshair")
        self.rings = QCheckBox("Concentric circles")
        self.spacing = QDoubleSpinBox()
        self.spacing.setRange(1, 100000)
        self.spacing.setDecimals(1)
        self.spacing.setValue(50)
        self.spacing.setSuffix(" raw px")
        self.ring_count = QSpinBox()
        self.ring_count.setRange(1, 20)
        self.ring_count.setValue(3)
        controls.setSpacing(22)
        controls.addWidget(self.crosshair)
        controls.addWidget(self.rings)
        spacing_controls = QHBoxLayout()
        spacing_controls.setSpacing(6)
        spacing_controls.addWidget(QLabel("Spacing"))
        spacing_controls.addWidget(self.spacing)
        controls.addLayout(spacing_controls)
        count_controls = QHBoxLayout()
        count_controls.setSpacing(6)
        count_controls.addWidget(QLabel("Count"))
        count_controls.addWidget(self.ring_count)
        controls.addLayout(count_controls)
        controls.addStretch(1)
        self.overlay_layout.addLayout(controls)
        annotations = QHBoxLayout()
        self.draw_mode = QCheckBox("Draw annotated circles")
        self.label_text = QLineEdit()
        self.label_text.setMaxLength(80)
        self.label_text.setPlaceholderText("Label, or automatic Circle 1, Circle 2...")
        self.undo_button = QPushButton("Undo annotation")
        self.clear_annotations_button = QPushButton("Clear annotations")
        annotations.addWidget(self.draw_mode)
        annotations.addWidget(self.label_text, 1)
        annotations.addWidget(self.undo_button)
        annotations.addWidget(self.clear_annotations_button)
        self.overlay_layout.addLayout(annotations)
        self.annotation_status = QLabel("Drag from circle centre to edge. Radii are raw pixels, not calibrated distances.")
        self.annotation_status.setWordWrap(True)
        self.overlay_layout.addWidget(self.annotation_status)
        self.surface.message.connect(self.annotation_status.setText)
        self.surface.changed.connect(self.annotation_changed)
        self.undo_button.clicked.connect(self.surface.undo)
        self.clear_annotations_button.clicked.connect(self.surface.clear)
        self.draw_mode.toggled.connect(self.overlay_changed)
        self.label_text.textChanged.connect(self.overlay_changed)
        for widget in (self.crosshair, self.rings):
            widget.toggled.connect(self.overlay_changed)
        self.spacing.valueChanged.connect(self.overlay_changed)
        self.ring_count.valueChanged.connect(self.overlay_changed)
        self.source.currentIndexChanged.connect(self.source_changed)
        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self.surface)
        self.undo_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.undo_shortcut.activated.connect(self.surface.undo)
        self.overlay_changed()
        self.annotation_changed()
        self.source_changed()

    def overlay_changed(self):
        self.surface.annotations.configure(crosshair=self.crosshair.isChecked(), rings=self.rings.isChecked(),
                                           spacing=self.spacing.value(), count=self.ring_count.value())
        self.surface.draw_circles = self.draw_mode.isChecked()
        self.surface.annotation_label = self.label_text.text()
        if not self.surface.draw_circles:
            self.surface.cancel_drag()
        self.surface.update()

    def annotation_changed(self):
        self.undo_button.setEnabled(self.surface.annotations.can_undo)
        self.clear_annotations_button.setEnabled(bool(self.surface.annotations.circles))

    def source_changed(self):
        if self.busy:
            return
        simulated = self.source.currentData() == "simulation"
        self.sim_dark.setEnabled(simulated)
        self.source_notice.setText("SIMULATION SELECTED: generated images only; no hardware connection" if simulated
                                   else "REAL CAMERA SELECTED: Start opens the first available UC480; no automatic fallback")
        self.setWindowTitle("Camera preview - SIMULATED" if simulated else "Camera preview - REAL UC480")
        self.surface.synthetic = simulated
        self.clear_dark()
        self.surface.annotations.reset()
        self.surface.annotations.geometry = None
        self.surface.cancel_drag()
        self.surface.clear_image()
        self._last_packet = None
        self.mailbox.take()
        self.surface.update()
        self.annotation_changed()

    def _synthetic_factory(self, **kwargs):
        return SimulatedCamera(**kwargs, illumination=self._illumination, stop_event=self._stop)

    def start(self):
        if self.busy:
            return
        simulated = self.source.currentData() == "simulation"
        self._source_mode = "simulation" if simulated else "real"
        self._factory = self._synthetic_factory if simulated else self._real_factory
        self._reserve = None if simulated else self._real_reserve
        # Each new connection may be a different physical camera; do not imply
        # registration. Dark context checks remain in the original processor.
        self.surface.annotations.reset()
        self.surface.cancel_drag()
        self.annotation_changed()
        self.gain.setMaximum(100)
        self.source.setEnabled(False)
        super().start()
        if not self.busy:
            self.source.setEnabled(True)

    def reject(self):
        # QDialog Escape normally hides without closeEvent. Keep the same safe
        # worker-stop/cleanup path as the window close button.
        self.close()

    def _worker_finished(self):
        super()._worker_finished()
        self.source.setEnabled(True)

    def draw_latest(self):
        # Base draw takes only the newest packet. Its set_pixels triggers an update;
        # painting occurs after this slot, so geometry is set before overlays paint.
        super().draw_latest()
        if self._last_packet is not None:
            shape = self._last_packet.raw_shape
            geometry = (int(shape[1]), int(shape[0]))
            if self.surface.annotations.geometry != geometry:
                self.surface.set_geometry(shape)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Standalone camera overlay/dark preview; defaults to simulation")
    parser.add_argument("--simulate", action="store_true", help="Explicit synthetic preview; no native camera imports")
    parser.parse_args(argv)
    if QApplication.instance() is not None:
        raise RuntimeError("Launch camera preview in its own process")
    app = QApplication([sys.argv[0]])
    window = CameraWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
