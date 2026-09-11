"""PyQt6 GUI for resumable one- or two-channel intensity maps.

Install as ``src/labtools/gui/intensity_map_gui.py``.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from labtools.acquisition.intensity_map import (
    IntensityMapConfig,
    IntensityMapSnapshot,
    acquire_intensity_map,
    config_from_resume_directory,
    estimated_minimum_duration_s,
)
from labtools.visualisation.intensity_map import update_map_axes


class MapWorker(QObject):
    progress = pyqtSignal(object)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str, str)

    def __init__(self, config: IntensityMapConfig, resume_directory: Path | None):
        super().__init__()
        self.config = config
        self.resume_directory = resume_directory
        self._cancel = False

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = acquire_intensity_map(
                self.config,
                resume_directory=self.resume_directory,
                progress_callback=self.progress.emit,
                cancel_requested=lambda: self._cancel,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc), traceback.format_exc())
        else:
            self.finished.emit(result)

    @pyqtSlot()
    def cancel(self) -> None:
        self._cancel = True


class IntensityMapWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("labtools intensity map")
        self.resize(1150, 720)
        self._thread: QThread | None = None
        self._worker: MapWorker | None = None
        self._resume_directory: Path | None = None

        splitter = QSplitter()
        controls = QWidget()
        control_layout = QVBoxLayout(controls)
        control_layout.addWidget(self._build_scan_group())
        control_layout.addWidget(self._build_controller_group())
        control_layout.addWidget(self._build_output_group())
        control_layout.addStretch(1)

        plot_widget = QWidget()
        plot_layout = QVBoxLayout(plot_widget)
        self.figure = Figure(figsize=(7, 6))
        self.canvas = FigureCanvas(self.figure)
        self.axes = self.figure.subplots()
        self.image = self.axes.imshow(
            np.full((2, 2), np.nan),
            origin="lower",
            aspect="auto",
            interpolation="nearest",
            cmap="inferno",
        )
        self.colourbar = self.figure.colorbar(self.image, ax=self.axes, pad=0.03)
        self.colourbar.set_label("Count rate (counts s$^{-1}$)")
        self.axes.set_xlabel("Mirror X voltage (V)")
        self.axes.set_ylabel("Mirror Y voltage (V)")
        self.axes.set_title("Intensity map")
        plot_layout.addWidget(self.canvas)

        self.progress = QProgressBar()
        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        plot_layout.addWidget(self.progress)
        plot_layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start new map")
        self.resume_button = QPushButton("Resume map...")
        self.stop_button = QPushButton("Stop after current point")
        self.stop_button.setEnabled(False)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.resume_button)
        buttons.addWidget(self.stop_button)
        plot_layout.addLayout(buttons)

        splitter.addWidget(controls)
        splitter.addWidget(plot_widget)
        splitter.setSizes([360, 790])
        self.setCentralWidget(splitter)

        self.start_button.clicked.connect(self.start_new)
        self.resume_button.clicked.connect(self.choose_resume)
        self.stop_button.clicked.connect(self.request_stop)
        self._update_estimate()

    def _build_scan_group(self) -> QGroupBox:
        group = QGroupBox("Scan")
        form = QFormLayout(group)
        self.x_start = self._voltage_box(-2.2)
        self.x_stop = self._voltage_box(-1.8)
        self.x_points = self._points_box(3)
        self.y_start = self._voltage_box(-0.7)
        self.y_stop = self._voltage_box(-0.3)
        self.y_points = self._points_box(3)

        x_row = QWidget()
        x_layout = QGridLayout(x_row)
        x_layout.setContentsMargins(0, 0, 0, 0)
        for column, (label, widget) in enumerate(
            [("Start", self.x_start), ("Stop", self.x_stop), ("Points", self.x_points)]
        ):
            x_layout.addWidget(QLabel(label), 0, column)
            x_layout.addWidget(widget, 1, column)
        form.addRow("X", x_row)

        y_row = QWidget()
        y_layout = QGridLayout(y_row)
        y_layout.setContentsMargins(0, 0, 0, 0)
        for column, (label, widget) in enumerate(
            [("Start", self.y_start), ("Stop", self.y_stop), ("Points", self.y_points)]
        ):
            y_layout.addWidget(QLabel(label), 0, column)
            y_layout.addWidget(widget, 1, column)
        form.addRow("Y", y_row)

        self.settle = QDoubleSpinBox()
        self.settle.setRange(0.0, 10.0)
        self.settle.setDecimals(3)
        self.settle.setValue(0.010)
        self.settle.setSuffix(" s")
        form.addRow("Mirror settle time", self.settle)
        self.serpentine = QCheckBox("Use serpentine scan order")
        self.serpentine.setChecked(True)
        form.addRow("", self.serpentine)

        for box in (
            self.x_start,
            self.x_stop,
            self.x_points,
            self.y_start,
            self.y_stop,
            self.y_points,
            self.settle,
        ):
            box.valueChanged.connect(self._update_estimate)
        return group

    def _build_controller_group(self) -> QGroupBox:
        group = QGroupBox("Time Controller")
        form = QFormLayout(group)
        self.address = QLineEdit("169.254.99.159")
        self.integration = QDoubleSpinBox()
        self.integration.setRange(0.001, 3600.0)
        self.integration.setDecimals(3)
        self.integration.setValue(0.100)
        self.integration.setSuffix(" s")
        self.integration.valueChanged.connect(self._update_estimate)
        self.channel_1 = QComboBox()
        self.channel_1.addItems(["1", "2", "3", "4"])
        self.use_second = QCheckBox("Acquire second channel")
        self.channel_2 = QComboBox()
        self.channel_2.addItems(["1", "2", "3", "4"])
        self.channel_2.setCurrentText("2")
        self.channel_2.setEnabled(False)
        self.use_second.toggled.connect(self.channel_2.setEnabled)
        form.addRow("Address", self.address)
        form.addRow("Integration time", self.integration)
        form.addRow("Primary channel", self.channel_1)
        form.addRow("", self.use_second)
        form.addRow("Second channel", self.channel_2)
        return group

    def _build_output_group(self) -> QGroupBox:
        group = QGroupBox("Output")
        form = QFormLayout(group)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        self.output_root = QLineEdit("C:/LabData/IntensityMaps")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._choose_output)
        layout.addWidget(self.output_root)
        layout.addWidget(browse)
        form.addRow("Output root", row)
        self.estimate = QLabel()
        form.addRow("Minimum estimate", self.estimate)
        return group

    @staticmethod
    def _voltage_box(value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(-10.0, 10.0)
        box.setDecimals(4)
        box.setValue(value)
        box.setSuffix(" V")
        return box

    @staticmethod
    def _points_box(value: int) -> QSpinBox:
        box = QSpinBox()
        box.setRange(2, 10000)
        box.setValue(value)
        return box

    def _channels(self) -> tuple[int, ...]:
        first = int(self.channel_1.currentText())
        if not self.use_second.isChecked():
            return (first,)
        second = int(self.channel_2.currentText())
        return first, second

    def _config(self) -> IntensityMapConfig:
        return IntensityMapConfig(
            x_start_v=self.x_start.value(),
            x_stop_v=self.x_stop.value(),
            x_points=self.x_points.value(),
            y_start_v=self.y_start.value(),
            y_stop_v=self.y_stop.value(),
            y_points=self.y_points.value(),
            integration_time_s=self.integration.value(),
            channels=self._channels(),
            settle_time_s=self.settle.value(),
            time_controller_address=self.address.text().strip(),
            serpentine=self.serpentine.isChecked(),
            output_root=Path(self.output_root.text().strip()),
        )

    def _apply_config(self, config: IntensityMapConfig) -> None:
        self.x_start.setValue(config.x_start_v)
        self.x_stop.setValue(config.x_stop_v)
        self.x_points.setValue(config.x_points)
        self.y_start.setValue(config.y_start_v)
        self.y_stop.setValue(config.y_stop_v)
        self.y_points.setValue(config.y_points)
        self.integration.setValue(config.integration_time_s)
        self.settle.setValue(config.settle_time_s)
        self.address.setText(config.time_controller_address)
        self.channel_1.setCurrentText(str(config.channels[0]))
        self.use_second.setChecked(len(config.channels) == 2)
        if len(config.channels) == 2:
            self.channel_2.setCurrentText(str(config.channels[1]))
        self.serpentine.setChecked(config.serpentine)
        self.output_root.setText(str(config.output_root))

    def _update_estimate(self) -> None:
        try:
            seconds = estimated_minimum_duration_s(self._config())
        except (AttributeError, ValueError):
            return
        self.estimate.setText(f"{seconds:.1f} s plus communication overhead")

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select output root", self.output_root.text()
        )
        if directory:
            self.output_root.setText(directory)

    def start_new(self) -> None:
        self._resume_directory = None
        self._start_worker(self._config())

    def choose_resume(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select incomplete map directory", self.output_root.text()
        )
        if not directory:
            return
        try:
            config = config_from_resume_directory(directory)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Cannot resume map", str(exc))
            return
        self._resume_directory = Path(directory)
        self._apply_config(config)
        self._start_worker(config)

    def _start_worker(self, config: IntensityMapConfig) -> None:
        try:
            config.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid map settings", str(exc))
            return
        self.start_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress.setValue(0)
        self.status.setText("Starting acquisition...")

        self._thread = QThread(self)
        self._worker = MapWorker(config, self._resume_directory)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def request_stop(self) -> None:
        self.stop_button.setEnabled(False)
        self.status.setText("Stopping after the current point and saving checkpoint...")
        if self._worker is not None:
            self._worker.cancel()

    @pyqtSlot(object)
    def _on_progress(self, snapshot: IntensityMapSnapshot) -> None:
        percent = int(100 * snapshot.points_complete / snapshot.total_points)
        self.progress.setValue(percent)
        title = (
            f"Channels {' + '.join(map(str, snapshot.channels))}: "
            f"{snapshot.points_complete}/{snapshot.total_points}"
        )
        if self.image.get_array().shape != snapshot.summed_count_rate_cps.shape:
            self.colourbar.remove()
            self.axes.clear()
            self.image = self.axes.imshow(
                snapshot.summed_count_rate_cps,
                origin="lower",
                extent=(
                    float(snapshot.x_values_v.min()),
                    float(snapshot.x_values_v.max()),
                    float(snapshot.y_values_v.min()),
                    float(snapshot.y_values_v.max()),
                ),
                aspect="auto",
                interpolation="nearest",
                cmap="inferno",
            )
            self.axes.set_xlabel("Mirror X voltage (V)")
            self.axes.set_ylabel("Mirror Y voltage (V)")
            self.colourbar = self.figure.colorbar(
                self.image,
                ax=self.axes,
                pad=0.03,
            )
            self.colourbar.set_label("Count rate (counts s$^{-1}$)")
        update_map_axes(
            self.axes,
            self.image,
            snapshot.summed_count_rate_cps,
            title=title,
        )
        self.colourbar.update_normal(self.image)
        self.canvas.draw_idle()
        self.status.setText(
            f"Elapsed: {snapshot.elapsed_s:.1f} s\nOutput: {snapshot.output_directory}"
        )

    @pyqtSlot(object)
    def _on_finished(self, result) -> None:
        status = "completed" if result.complete else "stopped with checkpoint saved"
        self.status.setText(f"Map {status}.\nOutput: {result.output_directory}")
        self.progress.setValue(100 if result.complete else self.progress.value())

    @pyqtSlot(str, str)
    def _on_failed(self, message: str, details: str) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("Intensity-map acquisition failed")
        dialog.setText(message)
        dialog.setDetailedText(details)
        dialog.exec()
        self.status.setText("Acquisition failed. Partial checkpoint was retained.")

    @pyqtSlot()
    def _cleanup_worker(self) -> None:
        self.start_button.setEnabled(True)
        self.resume_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None


def main() -> None:
    app = QApplication(sys.argv)
    window = IntensityMapWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()