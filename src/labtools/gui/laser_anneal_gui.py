"""PyQt6 GUI for no-pause scanning-mirror laser annealing."""

from __future__ import annotations

import sys
from pathlib import Path
from threading import Event

from PyQt6.QtCore import QObject, QSettings, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
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

from labtools.config.anneal_types import (
    AnnealProgress,
    LaserAnnealConfig,
    LaserAnnealResult,
)

# labtools operator workspace v1
from labtools.config.anneal_workspace import (
    resolve_gui_config,
    validate_stage_coordinate,
)


# Native constructors remain lazy; merely displaying an embedded panel does no I/O.
def run_laser_anneal(*args, **kwargs):
    from labtools.acquisition.laser_anneal import run_laser_anneal as run

    return run(*args, **kwargs)


def KinesisRotationStage(*args, **kwargs):
    from labtools.devices.kinesis_rotation_stage import KinesisRotationStage as stage

    return stage(*args, **kwargs)


def SC10(*args, **kwargs):
    from labtools.devices.sc10 import SC10 as shutter

    return shutter(*args, **kwargs)



from labtools.gui.error_formatting import format_operator_exception
from labtools.gui.recipe_controls import setup_recipe_controls


class AnnealWorker(QObject):
    """Run a blocking anneal acquisition in a worker thread."""

    progress = pyqtSignal(object)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, config: LaserAnnealConfig, stop_event: Event, acquisition=None) -> None:
        super().__init__()
        self.config = config
        self.stop_event = stop_event
        self._acquisition = acquisition if acquisition is not None else run_laser_anneal

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self._acquisition(
                self.config,
                stop_event=self.stop_event,
                progress_callback=self.progress.emit,
                status_callback=self.status.emit,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(format_operator_exception(exc))
        else:
            self.completed.emit(result)


class LaserAnnealWindow(QMainWindow):
    """Laser anneal controls with a live Thorlabs UC480 camera preview."""

    def __init__(self, *, acquisition=None, recipe_controls=True, camera_window=None) -> None:
        super().__init__()
        self._acquisition = acquisition
        self._settings = QSettings(
            "labtools",
            "LaserAnneal",
        )
        self.setWindowTitle("Laser Anneal")
        self.resize(1440, 900)
        self._thread: QThread | None = None
        self._worker: AnnealWorker | None = None
        self._stop_event = Event()
        from labtools.gui.camera_window import CameraWindow

        self._owns_camera_window = camera_window is None
        self.camera_window = CameraWindow(self) if camera_window is None else camera_window
        self.camera_exposure_ms = self.camera_window.exposure_ms
        self.camera_gain = self.camera_window.gain
        self.camera_interval_ms = self.camera_window.display_ms
        self.start_camera_button = self.camera_window.start_button
        self.stop_camera_button = self.camera_window.stop_button
        self.camera_status = self.camera_window.status

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
        self.open_camera_button = QPushButton("Open camera window")
        self.open_camera_button.clicked.connect(self._start_camera)
        control_layout.addWidget(self.open_camera_button)

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

        preview_group = QGroupBox("Annealing status")
        preview_layout = QVBoxLayout(preview_group)
        main_row.addWidget(preview_group, 1)
        camera_note = QLabel("Camera preview is now an independent window. "
                             "Use Open camera window to view it alongside any workflow.")
        camera_note.setWordWrap(True)
        preview_layout.addWidget(camera_note)
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

        self._restore_settings()
        self._update_estimate()
        self._apply_style()
        if recipe_controls:
            setup_recipe_controls(self)

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
        config = LaserAnnealConfig(
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
        return resolve_gui_config(config)

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
        try:
            validate_stage_coordinate(coordinate)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Instrument profile error", str(exc))
            return

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

        except Exception as exc:  # noqa: BLE001 - GUI reports vendor move failures
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

    @property
    def _camera_thread(self):
        return self.camera_window._thread if self._owns_camera_window else None

    def _start_camera(self):
        # Opening a modeless window does not start acquisition.
        self.camera_window.show()
        self.camera_window.raise_()
        self.camera_window.activateWindow()

    def _stop_camera(self):
        self.camera_window.request_stop()

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
        self._start_worker(config)

    def _start_worker(self, config):
        self._stop_event.clear()
        self._thread = QThread(self)
        self._worker = AnnealWorker(config, self._stop_event, acquisition=self._acquisition)
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
        if self._owns_camera_window and not self.camera_window.close():
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
