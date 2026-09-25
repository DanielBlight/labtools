"""PyQt6 GUI for no-pause scanning-mirror laser annealing."""

from __future__ import annotations

import sys
from pathlib import Path
from threading import Event

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from labtools.acquisition.laser_anneal import (
    AnnealProgress,
    LaserAnnealConfig,
    LaserAnnealResult,
    run_laser_anneal,
)
from labtools.devices.sc10 import SC10


class AnnealWorker(QObject):
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


class LaserAnnealWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Laser Anneal")
        self.resize(1280, 820)
        self._thread: QThread | None = None
        self._worker: AnnealWorker | None = None
        self._stop_event = Event()

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
        controls.setMaximumWidth(430)
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

        hardware_group = QGroupBox("SC10 shutter controller")
        hardware_form = QFormLayout(hardware_group)
        control_layout.addWidget(hardware_group)
        self.sc10_port = QLineEdit("COM4")
        hardware_form.addRow("COM port", self.sc10_port)
        self.test_sc10 = QPushButton("Test SC10")
        self.test_sc10.clicked.connect(self._test_sc10)
        hardware_form.addRow(self.test_sc10)

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

        plot_group = QGroupBox("Anneal path")
        plot_layout = QVBoxLayout(plot_group)
        main_row.addWidget(plot_group, 1)
        self.figure = Figure(figsize=(7, 6))
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self.figure)
        plot_layout.addWidget(self.canvas, 1)
        self.progress = QProgressBar()
        plot_layout.addWidget(self.progress)
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
        self._prepare_plot()
        self._update_estimate()
        self._apply_style()

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

    def _prepare_plot(self) -> None:
        self.axes.clear()
        self.axes.set_title("Configured anneal area")
        self.axes.set_xlabel("Mirror X voltage (V)")
        self.axes.set_ylabel("Mirror Y voltage (V)")
        self.axes.set_xlim(self.x_start.value(), self.x_stop.value())
        self.axes.set_ylim(self.y_start.value(), self.y_stop.value())
        self.marker = self.axes.plot([], [], "o", color="tab:red")[0]
        self.figure.subplots_adjust(left=0.13, right=0.96, bottom=0.12, top=0.92)
        self.canvas.draw_idle()

    def _test_sc10(self) -> None:
        try:
            with SC10(port=self.sc10_port.text().strip(), baud_rate=9600) as shutter:
                state = shutter.get_state()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "SC10 test failed", str(exc))
        else:
            QMessageBox.information(self, "SC10 test passed", str(state))

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
        self._prepare_plot()
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
        self.marker.set_data([update.x_voltage_v], [update.y_voltage_v])
        self.canvas.draw_idle()
        self.status.setText(
            f"Pass {update.pass_index}/{update.passes} | {update.sequence:,}/{update.total_points:,} | "
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
        else:
            event.accept()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget { background: #f5f7fa; color: #102a43; font-size: 9pt; }
            QLabel#title { font-size: 20pt; font-weight: 700; }
            QLabel#state { background: #343a40; color: white; border-radius: 8px; padding: 8px 18px; }
            QGroupBox { background: white; border: 1px solid #d7e1ea; border-radius: 9px; margin-top: 12px; padding: 12px; font-weight: 600; }
            QLineEdit, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #b8c7d4; border-radius: 5px; padding: 5px; }
            QPushButton { background: white; border: 1px solid #9fb5c8; border-radius: 5px; padding: 7px; }
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
