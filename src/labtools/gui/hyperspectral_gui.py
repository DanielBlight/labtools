"""Simulation-first operator GUI over the public hyperspectral facade."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from labtools.config.hyperspectral import HyperspectralConfig
from labtools.config.spectrum import SpectrumSettings
from labtools.measurements import HyperspectralRequest, load_dark

from .hyperspectral_controller import HyperspectralController
from .hyperspectral_view import build_view


class HyperspectralWindow(QMainWindow):
    def __init__(self, parent=None, *, controller=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hyperspectral acquisition (simulation)")
        self.controller = controller or HyperspectralController(self)
        self.last_measurement = None
        self._close_after_cleanup = False
        self._state = "idle"
        self.dark_record = None
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        form = QFormLayout()
        layout.addLayout(form)
        self.configuration_id = QLineEdit("reviewed-hyperspectral-simulation-v1")
        self.backend = QComboBox()
        self.backend.addItem("Simulation", "simulation")
        self.preset = QComboBox()
        self.preset.addItems(["syncerity", "symphony"])
        self.exposure_s = self._double(0.1, 0.001, 10000.0)
        self.slit_width_mm = self._double(0.5, 0.001, 10.0)
        self.start_nm = self._double(500.0, 0.0, 10000.0)
        self.end_nm = self._double(600.0, 0.0, 10000.0)
        self.x_start_v = self._double(0.0, -10.0, 10.0)
        self.x_stop_v = self._double(0.1, -10.0, 10.0)
        self.y_start_v = self._double(0.0, -10.0, 10.0)
        self.y_stop_v = self._double(0.1, -10.0, 10.0)
        self.x_points = self._integer(2)
        self.y_points = self._integer(2)
        self.settle_time_s = self._double(0.0, 0.0, 60.0)
        self.dark_mode = QComboBox()
        self.dark_mode.addItems(["none", "per_center", "per_frame", "pre_taken"])
        self.dark_path = QLineEdit()
        dark_browse = QPushButton("Load dark...")
        dark_browse.clicked.connect(self._browse_dark)
        dark_row = QHBoxLayout()
        dark_row.addWidget(self.dark_path)
        dark_row.addWidget(dark_browse)
        self.output_path = QLineEdit()
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_path)
        output_row.addWidget(browse)
        for label, widget in [
            ("Reviewed configuration ID", self.configuration_id),
            ("Backend", self.backend),
            ("Detector preset", self.preset),
            ("Exposure (s)", self.exposure_s),
            ("Slit width (mm)", self.slit_width_mm),
            ("Start wavelength (nm)", self.start_nm),
            ("End wavelength (nm)", self.end_nm),
            ("X start (V)", self.x_start_v),
            ("X stop (V)", self.x_stop_v),
            ("X points", self.x_points),
            ("Y start (V)", self.y_start_v),
            ("Y stop (V)", self.y_stop_v),
            ("Y points", self.y_points),
            ("Settle time (s)", self.settle_time_s),
            ("Dark mode", self.dark_mode),
        ]:
            form.addRow(label, widget)
        form.addRow("Pre-taken dark NPZ", dark_row)
        form.addRow("Output NPZ (optional)", output_row)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start simulation")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.status = QLabel("Idle")
        self.progress = QLabel("0 / 0 points")
        self.summary = QLabel("No dataset")
        self.pixel_y = self._integer(1)
        self.pixel_x = self._integer(1)
        self.select_button = QPushButton("Show selected spectrum")
        self.select_button.clicked.connect(self._select_pixel)
        pixel_row = QHBoxLayout()
        pixel_row.addWidget(QLabel("Y index"))
        pixel_row.addWidget(self.pixel_y)
        pixel_row.addWidget(QLabel("X index"))
        pixel_row.addWidget(self.pixel_x)
        pixel_row.addWidget(self.select_button)
        layout.addLayout(pixel_row)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addWidget(self.summary)
        self.start_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel)
        self.controller.progress.connect(self._progress)
        self.controller.finished.connect(self._finished)
        self.controller.failed.connect(self._failed)
        self.controller.idle.connect(self._idle)

    @staticmethod
    def _double(value, minimum, maximum):
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(6)
        box.setValue(value)
        return box

    @staticmethod
    def _integer(value):
        box = QSpinBox()
        box.setRange(1, 100000)
        box.setValue(value)
        return box

    def build_request(self):
        backend = self.backend.currentData()
        settings = SpectrumSettings(
            self.configuration_id.text().strip() + "-spectrum",
            self.preset.currentText(),
            self.exposure_s.value(),
            2,
            0,
            self.slit_width_mm.value(),
            self.start_nm.value(),
            self.end_nm.value(),
            backend=backend,
        )
        config = HyperspectralConfig(
            self.configuration_id.text().strip(),
            settings,
            self.x_start_v.value(),
            self.x_stop_v.value(),
            self.x_points.value(),
            self.y_start_v.value(),
            self.y_stop_v.value(),
            self.y_points.value(),
            self.settle_time_s.value(),
            self.dark_mode.currentText(),
            backend,
        )
        path = (
            Path(self.output_path.text()).expanduser().resolve()
            if self.output_path.text().strip()
            else None
        )
        request = HyperspectralRequest(config, path)
        request.validate()
        return request

    def start(self):
        try:
            request = self.build_request()
            self.controller.start(request)
        except Exception as exc:  # noqa: BLE001 - operator-visible GUI boundary
            QMessageBox.warning(self, "Invalid hyperspectral request", str(exc))
            return
        self._set_state("starting")
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

    def cancel(self):
        self.status.setText("Cancelling")
        self.cancel_button.setEnabled(False)
        self.controller.cancel()

    def _progress(self, event):
        self.status.setText(event.phase.replace("_", " ").title())
        self.progress.setText(f"{event.completed_points} / {event.total_points} points")

    def _finished(self, measurement):
        self.last_measurement = measurement
        result = measurement.result
        integrated = (
            np.nansum(result.intensity, axis=2)
            if result.intensity.ndim == 3
            else np.empty((0, 0))
        )
        self.status.setText(
            "Complete" if result.status == "complete" else "Cancelled with partial data"
        )
        self.summary.setText(
            f"Synthetic={measurement.provenance.synthetic}; cube={result.intensity.shape}; integrated map={integrated.shape}; output={result.output_path or 'not saved'}"
        )

    def _failed(self, message, traceback_text):
        self.status.setText("Failed")
        self.summary.setText(message)

    def _idle(self):
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def _set_state(self, state):
        self._state = state
        self.status.setText(state.replace("-", " ").title())
        busy = state in {"starting", "running", "cancelling", "cleanup-wait"}
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(state in {"starting", "running"})

    def _select_pixel(self):
        if self.last_measurement is None:
            self.summary.setText("No dataset available")
            return

        try:
            view = build_view(
                self.last_measurement.result,
                self.pixel_y.value() - 1,
                self.pixel_x.value() - 1,
            )
        except (IndexError, ValueError) as exc:
            self.summary.setText(str(exc))
            return

        self.summary.setText(
            "Selected spectrum: "
            f"{view.spectrum.size} points; "
            f"wavelength (nm) {view.wavelength_nm[0]:.3f} "
            f"to {view.wavelength_nm[-1]:.3f}; "
            f"mirror pixel ({view.y_index}, {view.x_index})"
        )

    def _browse_dark(self):
        value, _ = QFileDialog.getOpenFileName(
            self,
            "Pre-taken dark NPZ",
            filter="NumPy archive (*.npz)",
        )
        if not value:
            return

        try:
            self.dark_record = load_dark(Path(value))
        except Exception as exc:  # noqa: BLE001 - operator-visible GUI boundary
            QMessageBox.warning(self, "Invalid dark record", str(exc))
            return

        self.dark_path.setText(value)
        self.dark_mode.setCurrentText("pre_taken")
        self.summary.setText(f"Dark record loaded: {self.dark_record.record_id}")

    def _browse(self):
        value, _ = QFileDialog.getSaveFileName(
            self, "Hyperspectral NPZ", filter="NumPy archive (*.npz)"
        )
        if value:
            self.output_path.setText(value)

    def closeEvent(self, event):
        if self.controller.busy:
            self.cancel()
            event.ignore()
            return
        event.accept()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = HyperspectralWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
