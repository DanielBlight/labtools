"""PyQt6 GUI for no-pause scanning-mirror laser annealing."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from threading import Event, Lock

import numpy as np
from numpy.typing import NDArray
from PyQt6.QtCore import QObject, QSettings, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from labtools.acquisition.laser_anneal import (
    AnnealProgress,
    LaserAnnealConfig,
    LaserAnnealResult,
    run_laser_anneal,
)
from labtools.devices.kinesis_rotation_stage import KinesisRotationStage
from labtools.devices.sc10 import SC10
from labtools.devices.uc480_camera import ThorlabsUC480Camera


class AnnealWorker(QObject):
    """Run a blocking anneal acquisition in a worker thread."""

    progress = pyqtSignal(object)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, config: LaserAnnealConfig, stop_event: Event) -> None:
        super().__init__()
        self.config = config
        self.stop_event = stop_event

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = run_laser_anneal(
                self.config,
                stop_event=self.stop_event,
                progress_callback=self.progress.emit,
                status_callback=self.status.emit,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        else:
            self.completed.emit(result)


class CameraSettings:
    """Thread-safe target exposure and master gain settings."""

    def __init__(self, exposure_s: float, master_gain: float) -> None:
        self._lock = Lock()
        self._exposure_s = exposure_s
        self._master_gain = master_gain

    def update(self, exposure_s: float, master_gain: float) -> None:
        with self._lock:
            self._exposure_s = exposure_s
            self._master_gain = master_gain

    def snapshot(self) -> tuple[float, float]:
        with self._lock:
            return self._exposure_s, self._master_gain


class LatestCameraFrame:
    """Store only the newest complete camera frame."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._frame: NDArray[np.generic] | None = None

    def put(
        self,
        frame: NDArray[np.generic],
    ) -> None:
        """Replace the stored frame with the newest frame."""
        complete_frame = np.ascontiguousarray(frame)

        with self._lock:
            self._frame = complete_frame

    def take(
        self,
    ) -> NDArray[np.generic] | None:
        """Return and remove the newest available frame."""
        with self._lock:
            frame = self._frame
            self._frame = None

        return frame


class CameraWorker(QObject):
    """Acquire UC480 frames continuously in a worker thread."""

    frame_ready = pyqtSignal(object)
    connected = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        *,
        settings: CameraSettings,
        frame_buffer: LatestCameraFrame,
        frame_interval_s: float,
        stop_event: Event,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.frame_buffer = frame_buffer
        self.frame_interval_s = max(float(frame_interval_s), 0.016)
        self.stop_event = stop_event

    @pyqtSlot()
    def run(self) -> None:
        try:
            exposure_s, master_gain = self.settings.snapshot()
            with ThorlabsUC480Camera(exposure_s=exposure_s) as camera:
                maximum_gain = camera.get_max_gains()[0]
                applied_gain = camera.set_master_gain(master_gain)
                self.connected.emit(
                    {
                        "device_info": str(camera.get_device_info()),
                        "maximum_gain": maximum_gain,
                        "applied_gain": applied_gain,
                        "exposure_s": camera.get_exposure(),
                    }
                )
                applied_exposure = camera.get_exposure()
                camera.start_live(buffer_frames=20)

                while not self.stop_event.is_set():
                    requested_exposure, requested_gain = self.settings.snapshot()
                    settings_changed = False

                    if not np.isclose(requested_exposure, applied_exposure):
                        applied_exposure = camera.set_exposure(requested_exposure)
                        settings_changed = True

                    if not np.isclose(requested_gain, applied_gain):
                        applied_gain = camera.set_master_gain(requested_gain)
                        settings_changed = True

                    if settings_changed:
                        # UC480 can return transient or partially updated frames
                        # immediately after exposure or gain reconfiguration. Keep
                        # displaying the previous good frame while these settle.
                        for _ in range(3):
                            if self.stop_event.is_set():
                                break
                            camera.read_latest(timeout_s=1.0)

                    started = time.monotonic()
                    self.frame_buffer.put(camera.read_latest(timeout_s=1.0))
                    remaining = self.frame_interval_s - (time.monotonic() - started)
                    if remaining > 0:
                        self.stop_event.wait(remaining)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class CameraDisplay(QLabel):
    """Aspect-ratio-preserving UC480 camera display."""

    def __init__(self) -> None:
        super().__init__("Camera preview stopped")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(640, 480)
        self.setObjectName("cameraDisplay")
        self._pixmap: QPixmap | None = None

    def set_frame(self, frame: NDArray[np.generic]) -> None:
        """Display a frame using ThorCam-compatible BGR-to-RGB ordering."""
        self._pixmap = QPixmap.fromImage(self._to_qimage(frame))
        self._refresh()

    def clear_frame(self, message: str = "Camera preview stopped") -> None:
        self._pixmap = None
        self.clear()
        self.setText(message)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._pixmap is None:
            return
        self.setPixmap(
            self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )

    @staticmethod
    def _display_uint8(values: NDArray[np.generic]) -> NDArray[np.uint8]:
        """Convert to 8-bit using one shared scale, never per-channel scales."""
        data = np.asarray(values)
        if data.dtype == np.uint8:
            return np.ascontiguousarray(data)

        floating = np.asarray(data, dtype=float)
        finite = floating[np.isfinite(floating)]
        if finite.size == 0:
            return np.zeros(floating.shape, dtype=np.uint8)

        lower, upper = np.percentile(finite, (0.1, 99.9))
        if upper <= lower:
            lower = float(np.min(finite))
            upper = float(np.max(finite))
        if upper <= lower:
            return np.zeros(floating.shape, dtype=np.uint8)

        scaled = (floating - lower) * (255.0 / (upper - lower))
        return np.ascontiguousarray(np.clip(scaled, 0, 255).astype(np.uint8))

    @classmethod
    def _to_qimage(cls, frame: NDArray[np.generic]) -> QImage:
        array = np.asarray(frame)

        if array.ndim == 2:
            grey = cls._display_uint8(array)
            height, width = grey.shape
            return QImage(
                grey.data,
                width,
                height,
                grey.strides[0],
                QImage.Format.Format_Grayscale8,
            ).copy()

        if array.ndim == 3 and array.shape[2] in {3, 4}:
            # UC480 colour buffers are delivered in BGR/BGRA order. Interpret
            # them as such before handing RGB data to Qt. A single shared
            # display transform preserves the camera's channel balance.
            bgr = array[..., :3]
            rgb = cls._display_uint8(bgr[..., ::-1])
            height, width, _ = rgb.shape
            return QImage(
                rgb.data,
                width,
                height,
                rgb.strides[0],
                QImage.Format.Format_RGB888,
            ).copy()

        raise ValueError(f"Unsupported camera frame shape: {array.shape}")


class LaserAnnealWindow(QMainWindow):
    """Laser anneal controls with a live Thorlabs UC480 camera preview."""

    def __init__(self) -> None:
        super().__init__()
        self._settings = QSettings(
            "labtools",
            "LaserAnneal",
        )
        self.setWindowTitle("Laser Anneal")
        self.resize(1440, 900)
        self._thread: QThread | None = None
        self._worker: AnnealWorker | None = None
        self._stop_event = Event()
        self._camera_thread: QThread | None = None
        self._camera_worker: CameraWorker | None = None
        self._camera_stop_event = Event()
        self._camera_settings = CameraSettings(0.020, 1.0)
        self._camera_frame_buffer = LatestCameraFrame()
        self._camera_display_timer = QTimer(self)
        self._camera_display_timer.setInterval(33)
        self._camera_display_timer.timeout.connect(self._draw_latest_camera_frame)

        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)

        title_row = QHBoxLayout()
        title = QLabel("Laser Anneal")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.shutter_state = QLabel("Shutter: closed until start")
        self.shutter_state.setObjectName("state")
        title_row.addWidget(self.shutter_state)
        root.addLayout(title_row)

        main_row = QHBoxLayout()
        root.addLayout(main_row, 1)
        controls = QWidget()
        controls.setMaximumWidth(440)
        control_layout = QVBoxLayout(controls)
        main_row.addWidget(controls)

        scan_group = QGroupBox("Scan configuration")
        scan_form = QFormLayout(scan_group)
        control_layout.addWidget(scan_group)
        self.x_start = self._voltage_box(-1.0)
        self.x_stop = self._voltage_box(1.0)
        self.x_points = self._points_box(2)
        self.y_start = self._voltage_box(1.0)
        self.y_stop = self._voltage_box(3.0)
        self.y_points = self._points_box(2)
        scan_form.addRow(
            "X range", self._range_row(self.x_start, self.x_stop, self.x_points)
        )
        scan_form.addRow(
            "Y range", self._range_row(self.y_start, self.y_stop, self.y_points)
        )
        self.passes = self._points_box(1)
        self.passes.setMaximum(1000)
        scan_form.addRow("Passes", self.passes)
        self.dwell = self._time_box(0.001)
        self.settle = self._time_box(0.0)
        scan_form.addRow("Point dwell", self.dwell)
        scan_form.addRow("Mirror settle", self.settle)
        self.serpentine = QCheckBox("Use serpentine scan order")
        scan_form.addRow(self.serpentine)

        self._make_collapsible(scan_group, initially_open=False)
        hardware_group = QGroupBox("SC10 shutter controller")
        hardware_form = QFormLayout(hardware_group)
        control_layout.addWidget(hardware_group)
        self.sc10_port = QLineEdit("COM4")
        hardware_form.addRow("COM port", self.sc10_port)
        self.test_sc10 = QPushButton("Test SC10")
        self.test_sc10.clicked.connect(self._test_sc10)
        hardware_form.addRow(self.test_sc10)

        self._make_collapsible(hardware_group, initially_open=False)
        stage_group = QGroupBox("Anneal power rotation stage")
        stage_form = QFormLayout(stage_group)
        control_layout.addWidget(stage_group)

        self.anneal_stage_coordinate = QDoubleSpinBox()
        self.anneal_stage_coordinate.setRange(-2147483648.0, 2147483647.0)
        self.anneal_stage_coordinate.setDecimals(0)
        self.anneal_stage_coordinate.setValue(35000.0)
        self.anneal_stage_coordinate.setToolTip(
            "Native controller coordinate used during laser annealing."
        )
        stage_form.addRow("Anneal coordinate", self.anneal_stage_coordinate)

        self.return_stage = QCheckBox("Move to return coordinate after anneal")
        self.return_stage.setChecked(True)
        stage_form.addRow(self.return_stage)

        self.return_stage_coordinate = QDoubleSpinBox()
        self.return_stage_coordinate.setRange(-2147483648.0, 2147483647.0)
        self.return_stage_coordinate.setDecimals(0)
        self.return_stage_coordinate.setValue(90000.0)
        stage_form.addRow("Return coordinate", self.return_stage_coordinate)

        self.test_stage = QPushButton("Test rotation stage")
        self.test_stage.clicked.connect(self._test_rotation_stage)
        stage_form.addRow(self.test_stage)

        self.move_to_anneal_stage = QPushButton("Move to anneal coordinate")
        self.move_to_anneal_stage.clicked.connect(self._move_stage_to_anneal)
        stage_form.addRow(self.move_to_anneal_stage)

        self._make_collapsible(stage_group, initially_open=False)
        camera_group = QGroupBox("UC480 camera")
        camera_form = QFormLayout(camera_group)
        control_layout.addWidget(camera_group)
        camera_note = QLabel("First available Thorlabs UC480 camera")
        camera_note.setWordWrap(True)
        camera_form.addRow("Camera", camera_note)
        self.camera_exposure_ms = QDoubleSpinBox()
        self.camera_exposure_ms.setRange(0.01, 10000.0)
        self.camera_exposure_ms.setDecimals(3)
        self.camera_exposure_ms.setValue(20.0)
        self.camera_exposure_ms.setSuffix(" ms")
        camera_form.addRow("Exposure", self.camera_exposure_ms)

        self.camera_gain = QDoubleSpinBox()
        self.camera_gain.setRange(1.0, 100.0)
        self.camera_gain.setDecimals(2)
        self.camera_gain.setSingleStep(0.25)
        self.camera_gain.setValue(1.0)
        self.camera_gain.setSuffix(" x")
        self.camera_gain.setToolTip(
            "Master hardware gain factor. The camera clamps this to its supported maximum."
        )
        camera_form.addRow("Master gain", self.camera_gain)

        self.camera_interval_ms = QDoubleSpinBox()
        self.camera_interval_ms.setRange(16.0, 10000.0)
        self.camera_interval_ms.setDecimals(0)
        self.camera_interval_ms.setValue(33.0)
        self.camera_interval_ms.setSuffix(" ms")
        camera_form.addRow("Extra display delay", self.camera_interval_ms)
        camera_buttons = QHBoxLayout()
        self.start_camera_button = QPushButton("Start camera")
        self.start_camera_button.clicked.connect(self._start_camera)
        self.stop_camera_button = QPushButton("Stop camera")
        self.stop_camera_button.clicked.connect(self._stop_camera)
        self.stop_camera_button.setEnabled(False)
        camera_buttons.addWidget(self.start_camera_button)
        camera_buttons.addWidget(self.stop_camera_button)
        camera_form.addRow(camera_buttons)

        self._make_collapsible(camera_group, initially_open=False)
        output_group = QGroupBox("Output and confirmation")
        output_form = QFormLayout(output_group)
        control_layout.addWidget(output_group)
        self.max_open = QDoubleSpinBox()
        self.max_open.setRange(1.0, 86400.0)
        self.max_open.setValue(900.0)
        self.max_open.setSuffix(" s")
        output_form.addRow("Maximum open time", self.max_open)
        self.output_root = QLineEdit("C:/LabData/LaserAnneal")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_root, 1)
        output_row.addWidget(browse)
        output_form.addRow("Output folder", output_row)
        self.save_log = QCheckBox("Save position log and metadata")
        self.save_log.setChecked(True)
        output_form.addRow(self.save_log)
        self.confirm = QCheckBox("I have checked the optical path and sample settings")
        self.confirm.toggled.connect(self._update_start_state)
        output_form.addRow(self.confirm)

        self._make_collapsible(output_group, initially_open=False)
        self.estimate = QLabel()
        control_layout.addWidget(self.estimate)
        self.start_button = QPushButton("Start anneal")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self._start)
        self.start_button.setEnabled(False)
        control_layout.addWidget(self.start_button)
        self.stop_button = QPushButton("Stop after current point")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        control_layout.addWidget(self.stop_button)
        control_layout.addStretch(1)

        preview_group = QGroupBox("Live camera")
        preview_layout = QVBoxLayout(preview_group)
        main_row.addWidget(preview_group, 1)
        self.camera_display = CameraDisplay()
        preview_layout.addWidget(self.camera_display, 1)
        self.camera_status = QLabel("Camera stopped")
        preview_layout.addWidget(self.camera_status)
        self.progress = QProgressBar()
        preview_layout.addWidget(self.progress)
        self.status = QLabel("Ready")
        root.addWidget(self.status)

        for widget in (
            self.x_points,
            self.y_points,
            self.passes,
            self.dwell,
            self.settle,
        ):
            widget.valueChanged.connect(self._update_estimate)

        self.camera_exposure_ms.valueChanged.connect(self._update_camera_settings)
        self.camera_gain.valueChanged.connect(self._update_camera_settings)
        self._restore_settings()
        self._update_camera_settings()
        self._update_estimate()
        self._apply_style()

    def _make_collapsible(
        self,
        group: QGroupBox,
        *,
        initially_open: bool,
    ) -> QToolButton:
        """Add a disclosure-arrow row and hide complete form rows safely."""
        title = group.title()
        group.setTitle("")
        group.setCheckable(False)
        layout = group.layout()
        if not isinstance(layout, QFormLayout):
            raise TypeError("Collapsible sections require a QFormLayout")

        toggle = QToolButton(group)
        toggle.setObjectName("sectionToggle")
        toggle.setText(title)
        toggle.setCheckable(True)
        toggle.setChecked(initially_open)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(
            Qt.ArrowType.DownArrow if initially_open else Qt.ArrowType.RightArrow
        )
        toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toggle.setMinimumHeight(24)
        layout.insertRow(0, toggle)

        def set_expanded(expanded: bool) -> None:
            toggle.setArrowType(
                Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
            )
            for row in range(1, layout.rowCount()):
                layout.setRowVisible(row, expanded)
            group.adjustSize()
            group.updateGeometry()

        toggle.toggled.connect(set_expanded)
        set_expanded(initially_open)
        return toggle

    @staticmethod
    def _voltage_box(value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(-20.0, 20.0)
        box.setDecimals(4)
        box.setValue(value)
        return box

    @staticmethod
    def _points_box(value: int) -> QSpinBox:
        box = QSpinBox()
        box.setRange(1, 10000)
        box.setValue(value)
        return box

    @staticmethod
    def _time_box(value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(0.0, 10.0)
        box.setDecimals(4)
        box.setValue(value)
        box.setSuffix(" s")
        return box

    @staticmethod
    def _range_row(start, stop, points) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(start)
        layout.addWidget(stop)
        layout.addWidget(points)
        return widget

    def _restore_settings(self) -> None:
        """Restore values saved on the last clean GUI close."""
        value_widgets = {
            "x_start": (self.x_start, float),
            "x_stop": (self.x_stop, float),
            "x_points": (self.x_points, int),
            "y_start": (self.y_start, float),
            "y_stop": (self.y_stop, float),
            "y_points": (self.y_points, int),
            "passes": (self.passes, int),
            "point_dwell_s": (self.dwell, float),
            "mirror_settle_s": (self.settle, float),
            "anneal_coordinate": (
                self.anneal_stage_coordinate,
                float,
            ),
            "return_coordinate": (
                self.return_stage_coordinate,
                float,
            ),
            "camera_exposure_ms": (
                self.camera_exposure_ms,
                float,
            ),
            "camera_gain": (
                self.camera_gain,
                float,
            ),
            "camera_interval_ms": (
                self.camera_interval_ms,
                float,
            ),
            "maximum_open_time_s": (
                self.max_open,
                float,
            ),
        }

        for key, (
            widget,
            value_type,
        ) in value_widgets.items():
            saved = self._settings.value(
                key,
                None,
                type=value_type,
            )

            if saved is not None:
                widget.setValue(saved)

        check_widgets = {
            "serpentine": self.serpentine,
            "return_rotation_stage": (self.return_stage),
            "save_run_log": self.save_log,
        }

        for key, widget in check_widgets.items():
            saved = self._settings.value(
                key,
                None,
                type=bool,
            )

            if saved is not None:
                widget.setChecked(saved)

        text_widgets = {
            "sc10_port": self.sc10_port,
            "output_root": self.output_root,
        }

        for key, widget in text_widgets.items():
            saved = self._settings.value(
                key,
                None,
                type=str,
            )

            if saved:
                widget.setText(saved)

        # Never restore the safety acknowledgement.
        self.confirm.setChecked(False)

    def _save_settings(self) -> None:
        """Save values after all workers stop on a clean close."""
        values = {
            "x_start": self.x_start.value(),
            "x_stop": self.x_stop.value(),
            "x_points": self.x_points.value(),
            "y_start": self.y_start.value(),
            "y_stop": self.y_stop.value(),
            "y_points": self.y_points.value(),
            "passes": self.passes.value(),
            "point_dwell_s": self.dwell.value(),
            "mirror_settle_s": self.settle.value(),
            "serpentine": (self.serpentine.isChecked()),
            "sc10_port": (self.sc10_port.text().strip()),
            "anneal_coordinate": (self.anneal_stage_coordinate.value()),
            "return_coordinate": (self.return_stage_coordinate.value()),
            "return_rotation_stage": (self.return_stage.isChecked()),
            "camera_exposure_ms": (self.camera_exposure_ms.value()),
            "camera_gain": (self.camera_gain.value()),
            "camera_interval_ms": (self.camera_interval_ms.value()),
            "maximum_open_time_s": (self.max_open.value()),
            "output_root": (self.output_root.text().strip()),
            "save_run_log": (self.save_log.isChecked()),
        }

        for key, value in values.items():
            self._settings.setValue(
                key,
                value,
            )

        self._settings.sync()

    def _build_config(self) -> LaserAnnealConfig:
        return LaserAnnealConfig(
            x_start_v=self.x_start.value(),
            x_stop_v=self.x_stop.value(),
            x_points=self.x_points.value(),
            y_start_v=self.y_start.value(),
            y_stop_v=self.y_stop.value(),
            y_points=self.y_points.value(),
            passes=self.passes.value(),
            point_dwell_s=self.dwell.value(),
            mirror_settle_s=self.settle.value(),
            serpentine=self.serpentine.isChecked(),
            sc10_port=self.sc10_port.text().strip(),
            anneal_rotation_coordinate=self.anneal_stage_coordinate.value(),
            return_rotation_coordinate=self.return_stage_coordinate.value(),
            return_rotation_stage=self.return_stage.isChecked(),
            output_root=Path(self.output_root.text().strip()),
            save_run_log=self.save_log.isChecked(),
            maximum_open_time_s=self.max_open.value(),
        )

    def _update_estimate(self) -> None:
        points = self.x_points.value() * self.y_points.value() * self.passes.value()
        seconds = points * (self.dwell.value() + self.settle.value())
        self.estimate.setText(
            f"Positions: {points:,} | Estimated open time: {seconds:.1f} s plus overhead"
        )
        self._update_start_state()

    def _update_start_state(self) -> None:
        self.start_button.setEnabled(self.confirm.isChecked() and self._thread is None)

    def _test_sc10(self) -> None:
        try:
            with SC10(port=self.sc10_port.text().strip(), baud_rate=9600) as shutter:
                state = shutter.get_state()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "SC10 test failed", str(exc))
        else:
            QMessageBox.information(self, "SC10 test passed", str(state))

    def _move_stage_to_anneal(self) -> None:
        """Move the power-control stage to the configured anneal coordinate."""
        if self._thread is not None:
            QMessageBox.warning(
                self,
                "Anneal running",
                "The rotation stage cannot be moved manually "
                "while an anneal is running.",
            )
            return

        coordinate = self.anneal_stage_coordinate.value()

        answer = QMessageBox.question(
            self,
            "Confirm rotation-stage move",
            "Move the power-control rotation stage "
            f"to coordinate {coordinate:g}?\n\n"
            "This may change the delivered laser power.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.move_to_anneal_stage.setEnabled(False)
        self.test_stage.setEnabled(False)

        self.status.setText(f"Moving rotation stage to coordinate {coordinate:g}")

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:
            with KinesisRotationStage() as stage:
                final_position = stage.move_to(coordinate)
                serial_number = stage.serial_number or "unknown"

        except Exception as exc:
            self.status.setText("Rotation-stage move failed")

            QMessageBox.critical(
                self,
                "Rotation stage move failed",
                str(exc),
            )

        else:
            self.status.setText(
                f"Rotation stage {serial_number} reached coordinate {final_position:g}"
            )

            QMessageBox.information(
                self,
                "Rotation stage move completed",
                f"Serial: {serial_number}\nCoordinate: {final_position:g}",
            )

        finally:
            QApplication.restoreOverrideCursor()

            self.move_to_anneal_stage.setEnabled(True)
            self.test_stage.setEnabled(True)

    def _test_rotation_stage(self) -> None:
        """Connect to the stage and report its current native coordinate."""
        try:
            with KinesisRotationStage() as stage:
                position = stage.get_position()
                detected_serial = stage.serial_number
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Rotation stage test failed", str(exc))
        else:
            QMessageBox.information(
                self,
                "Rotation stage test passed",
                f"Serial: {detected_serial}\nCurrent coordinate: {position:g}",
            )

    def _update_camera_settings(self) -> None:
        """Publish camera settings for application between frames."""
        self._camera_settings.update(
            self.camera_exposure_ms.value() / 1000.0,
            self.camera_gain.value(),
        )

    def _draw_latest_camera_frame(
        self,
    ) -> None:
        """Draw at most one newest frame on each timer tick."""
        frame = self._camera_frame_buffer.take()

        if frame is None:
            return

        array = np.asarray(frame)

        self.camera_display.set_frame(array)

        self.camera_status.setText(f"Live | shape {array.shape} | {array.dtype}")

    def _start_camera(self) -> None:
        if self._camera_thread is not None:
            return
        self._camera_stop_event.clear()
        self._camera_thread = QThread(self)
        self._update_camera_settings()
        self._camera_worker = CameraWorker(
            settings=self._camera_settings,
            frame_buffer=self._camera_frame_buffer,
            frame_interval_s=self.camera_interval_ms.value() / 1000.0,
            stop_event=self._camera_stop_event,
        )
        self._camera_worker.moveToThread(self._camera_thread)
        self._camera_thread.started.connect(self._camera_worker.run)
        self._camera_worker.connected.connect(self._on_camera_connected)
        self._camera_worker.failed.connect(self._on_camera_failed)
        self._camera_worker.finished.connect(self._camera_thread.quit)
        self._camera_thread.finished.connect(self._cleanup_camera_worker)
        self.start_camera_button.setEnabled(False)
        self.stop_camera_button.setEnabled(True)
        self.camera_status.setText("Connecting to camera...")
        self._camera_display_timer.start()
        self._camera_thread.start()

    def _stop_camera(self) -> None:
        if self._camera_thread is None:
            return
        self._camera_stop_event.set()
        self.stop_camera_button.setEnabled(False)
        self.camera_status.setText("Stopping camera...")

    @pyqtSlot(object)
    def _on_camera_frame(self, frame: object) -> None:
        array = np.asarray(frame)
        self.camera_display.set_frame(array)
        self.camera_status.setText(
            f"Live | shape {array.shape} | {array.dtype} | "
            f"min {np.min(array)} | max {np.max(array)}"
        )

    @pyqtSlot(object)
    def _on_camera_connected(self, information: object) -> None:
        details = dict(information)
        maximum_gain = float(details["maximum_gain"])
        self.camera_gain.blockSignals(True)
        self.camera_gain.setMaximum(maximum_gain)
        self.camera_gain.setValue(float(details["applied_gain"]))
        self.camera_gain.blockSignals(False)
        self._update_camera_settings()
        self.camera_status.setText(
            f"Camera connected: {details['device_info']} | "
            f"gain {details['applied_gain']:.2f}x / {maximum_gain:.2f}x max | "
            f"exposure {details['exposure_s'] * 1000.0:.3f} ms"
        )

    @pyqtSlot(str)
    def _on_camera_failed(self, error: str) -> None:
        self.camera_display.clear_frame("Camera preview unavailable")
        self.camera_status.setText(f"Camera error: {error}")
        QMessageBox.critical(self, "Camera preview failed", error)

    def _cleanup_camera_worker(self) -> None:
        self._camera_display_timer.stop()
        if self._camera_worker is not None:
            self._camera_worker.deleteLater()
        if self._camera_thread is not None:
            self._camera_thread.deleteLater()
        self._camera_worker = None
        self._camera_thread = None
        self.start_camera_button.setEnabled(True)
        self.stop_camera_button.setEnabled(False)
        if not self.camera_status.text().startswith("Camera error"):
            self.camera_status.setText("Camera stopped")

    def _start(self) -> None:
        try:
            config = self._build_config()
            config.validate()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Invalid configuration", str(exc))
            return
        answer = QMessageBox.question(
            self,
            "Confirm anneal",
            "Start the uninterrupted anneal scan with the current settings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._stop_event.clear()
        self._thread = QThread(self)
        self._worker = AnnealWorker(config, self._stop_event)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.status.connect(self._on_status)
        self._worker.completed.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self.progress.setRange(0, config.total_points)
        self.stop_button.setEnabled(True)
        self.start_button.setEnabled(False)
        self.shutter_state.setText("Shutter: preparing")
        self._thread.start()

    def _stop(self) -> None:
        self._stop_event.set()
        self.stop_button.setEnabled(False)
        self.status.setText("Stop requested; waiting for the current point")

    @pyqtSlot(str)
    def _on_status(self, message: str) -> None:
        self.status.setText(message)
        if message == "Shutter open; scanning":
            self.shutter_state.setText("Shutter: open")
        elif message in {"Closing shutter", "Returning mirror home", "Finished"}:
            self.shutter_state.setText("Shutter: closed")

    @pyqtSlot(object)
    def _on_progress(self, update: AnnealProgress) -> None:
        self.progress.setValue(update.sequence)
        self.status.setText(
            f"Pass {update.pass_index}/{update.passes} | "
            f"{update.sequence:,}/{update.total_points:,} | "
            f"X {update.x_voltage_v:.4f} V | Y {update.y_voltage_v:.4f} V"
        )

    @pyqtSlot(object)
    def _on_completed(self, result: LaserAnnealResult) -> None:
        self.shutter_state.setText("Shutter: closed")
        state = "stopped safely" if result.stopped else "completed"
        self.status.setText(
            f"Anneal {state}: {result.completed_points:,}/{result.total_points:,} points"
        )

    @pyqtSlot(str)
    def _on_failed(self, error: str) -> None:
        self.shutter_state.setText("Shutter: close command issued")
        QMessageBox.critical(self, "Laser anneal failed", error)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self.stop_button.setEnabled(False)
        self.confirm.setChecked(False)
        self._update_start_state()

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select output folder", self.output_root.text()
        )
        if path:
            self.output_root.setText(path)

    def closeEvent(self, event) -> None:
        if self._thread is not None:
            QMessageBox.warning(
                self,
                "Anneal running",
                "Stop the anneal and wait for cleanup before closing.",
            )
            event.ignore()
            return
        if self._camera_thread is not None:
            self._camera_stop_event.set()
            if not self._camera_thread.wait(3000):
                QMessageBox.warning(
                    self,
                    "Camera still stopping",
                    "Wait for the camera preview to stop before closing.",
                )
                event.ignore()
                return
        self._save_settings()
        event.accept()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #f5f7fa; color: #102a43; font-size: 9pt; }
            QLabel#title { font-size: 20pt; font-weight: 700; }
            QLabel#state { background: #343a40; color: white; border-radius: 8px; padding: 8px 18px; }
            QLabel#cameraDisplay { background: #101418; color: #d9e2ec; border: 1px solid #52606d; }
            QGroupBox { background: white; border: 1px solid #d7e1ea; border-radius: 9px; margin-top: 12px; padding: 12px; font-weight: 600; }
            QLineEdit { background: white; border: 1px solid #b8c7d4; border-radius: 5px; padding: 5px; }
            QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #b8c7d4; border-radius: 5px; padding: 0; padding-right: 18px; }
            QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button { width: 18px; }
            QPushButton { background: white; border: 1px solid #9fb5c8; border-radius: 5px; padding: 7px; }
            QToolButton#sectionToggle { border: none; background: transparent; font-weight: 650; padding: 2px; text-align: left; }
            QToolButton#sectionToggle:hover { color: #0b6fa4; }
            QPushButton#primary { background: #147eaf; color: white; font-weight: 700; }
            QProgressBar { background: white; border: 1px solid #b8c7d4; text-align: center; }
            QProgressBar::chunk { background: #147eaf; }
            """
        )


def main() -> None:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = LaserAnnealWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
