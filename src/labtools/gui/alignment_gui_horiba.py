"""Repeated HORIBA alignment display driven only through SpectrumWorker."""

from __future__ import annotations

import asyncio
import os
import sys
import traceback

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PyQt6.QtCore import QTimer, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.runtime.spectrum_backend import create_spectrum_service
from labtools.runtime.spectrum_worker import (
    SpectrumWorker,
    SpectrumWorkerBusyError,
    SpectrumWorkerFaultedError,
)


def detector_options(preset):
    from labtools.devices.horiba_spectrometer import HoribaSpectrometer

    return HoribaSpectrometer.preset_options(preset)


class HoribaAlignmentWindow(QMainWindow):
    """Own repeated submissions, never a HORIBA/backend/asyncio object."""

    def __init__(
        self,
        *,
        worker=None,
        configuration_id=None,
        backend="real",
        options_provider=detector_options,
    ):
        super().__init__()
        if backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        configuration_id = configuration_id or os.environ.get(
            "LABTOOLS_SPECTRUM_CONFIGURATION_ID"
        )
        if not configuration_id:
            raise ValueError(
                "A maintainer-supplied spectrum configuration_id is required"
            )
        self._configuration_id = configuration_id
        self._backend = backend
        self._options_provider = options_provider
        self._owns_worker = worker is None
        self._worker = worker or SpectrumWorker(
            create_spectrum_service(backend=backend), backend=backend
        )
        self._job = None
        self._running = False
        self._close_pending = False
        self._sequence = 0
        self._latest = None
        self.setWindowTitle("HORIBA Spectrum Alignment")
        self.resize(1200, 760)
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        title = QLabel("HORIBA Spectrum Alignment")
        root.addWidget(title)
        row = QHBoxLayout()
        root.addLayout(row, 1)
        controls = QVBoxLayout()
        row.addLayout(controls)
        self.setup_group = QGroupBox("Acquisition setup")
        form = QFormLayout(self.setup_group)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["syncerity", "symphony"])
        self.centre_box = self._number(0, 2200, 690, 3, " nm")
        self.exposure_box = self._number(0.001, 1000, 0.1, 3, " s")
        self.dark_checkbox = QCheckBox()
        self.gain_combo = QComboBox()
        self.speed_combo = QComboBox()
        for label, widget in (
            ("Detector preset", self.preset_combo),
            ("Centre wavelength", self.centre_box),
            ("Exposure", self.exposure_box),
            ("Dark subtraction", self.dark_checkbox),
            ("Gain", self.gain_combo),
            ("Readout speed", self.speed_combo),
        ):
            form.addRow(label, widget)
        controls.addWidget(self.setup_group)
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        self.autoscale = QCheckBox("Autoscale axes")
        self.autoscale.setChecked(True)
        controls.addWidget(self.autoscale)
        controls.addStretch(1)
        panel = QFrame()
        plot = QVBoxLayout(panel)
        row.addWidget(panel, 1)
        self.figure = Figure(figsize=(8, 5), tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Intensity (counts)")
        (self.line,) = self.axes.plot([], [], linewidth=1.2, color="#0b6fa4")
        self.canvas = FigureCanvas(self.figure)
        plot.addWidget(NavigationToolbar(self.canvas, self))
        plot.addWidget(self.canvas, 1)
        self.metrics = QLabel("No spectrum acquired")
        plot.addWidget(self.metrics)
        self.status_label = QLabel("Ready")
        root.addWidget(self.status_label)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._poll_job)
        self.start_button.clicked.connect(self.start_alignment)
        self.stop_button.clicked.connect(self.stop_alignment)
        self.preset_combo.currentTextChanged.connect(self._update_preset)
        self._update_preset()

    @staticmethod
    def _number(lower, upper, value, decimals, suffix):
        box = QDoubleSpinBox()
        box.setDecimals(decimals)
        box.setRange(lower, upper)
        box.setValue(value)
        box.setSuffix(suffix)
        return box

    def _update_preset(self):
        options = self._options_provider(self.preset_combo.currentText())
        for combo, field, default in (
            (self.gain_combo, "gains", "default_gain"),
            (self.speed_combo, "speeds", "default_speed"),
        ):
            combo.clear()
            for label, token in options[field]:
                combo.addItem(label, token)
            combo.setCurrentIndex(max(0, combo.findData(options[default])))
        self.exposure_box.setMinimum(float(options["minimum_exposure_s"]))

    def _snapshot_settings(self):
        settings = AlignmentSettings(
            self._configuration_id,
            self.preset_combo.currentText(),
            float(self.centre_box.value()),
            float(self.exposure_box.value()),
            self.dark_checkbox.isChecked(),
            int(self.gain_combo.currentData()),
            int(self.speed_combo.currentData()),
            self._backend,
        )
        settings.validate_detector(self._options_provider(settings.preset))
        return settings

    def start_alignment(self):
        if self._running:
            return
        try:
            settings = self._snapshot_settings()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Invalid alignment settings", str(exc))
            return
        self._running = True
        self._close_pending = False
        self._sequence = 0
        self.setup_group.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.timer.start()
        self._submit(settings)

    def _submit(self, settings):
        if not self._running:
            return
        try:
            self._job = self._worker.acquire_alignment(
                settings, owner="spectrum-alignment"
            )
            self.status_label.setText("Acquiring alignment spectrum...")
        except SpectrumWorkerBusyError as exc:
            self._finish(f"Spectrum resource busy: {exc}")
        except SpectrumWorkerFaultedError:
            self._finish("Spectrum worker faulted; application teardown is required")

    @pyqtSlot()
    def _poll_job(self):
        job = self._job
        if job is None or not job.done():
            return
        self._job = None
        try:
            result = job.result()
        except asyncio.CancelledError:
            self._finish("Stopped")
        except SpectrumWorkerFaultedError:
            self._finish("Spectrum worker faulted; application teardown is required")
        except BaseException:  # noqa: BLE001 - GUI reports worker job failures
            details = traceback.format_exc()
            self._finish("Alignment failed")
            box = QMessageBox(self)
            box.setWindowTitle("Alignment failed")
            box.setIcon(QMessageBox.Icon.Critical)
            box.setText(details.strip().splitlines()[-1])
            box.setDetailedText(details)
            box.exec()
        else:
            self._sequence += 1
            self._latest = result
            self.line.set_data(result.wavelength_nm, result.intensity)
            if self.autoscale.isChecked() or self._sequence == 1:
                self.axes.relim()
                self.axes.autoscale_view()
            identity = "dark-subtracted" if result.dark_subtracted else "raw"
            self.axes.set_ylabel(f"Intensity ({identity} counts)")
            self.axes.set_title(
                f"{result.settings.preset.title()} | centre {result.actual_centre_nm:.3f} nm"
            )
            self.metrics.setText(
                f"Frame {self._sequence} | peak {np.max(result.intensity):.6g} counts | "
                f"sum {np.sum(result.intensity):.6g} counts"
            )
            self.canvas.draw_idle()
            if self._running:
                self._submit(result.settings)
            else:
                self._finish("Stopped")

    def stop_alignment(self):
        if not self._running:
            return
        self._running = False
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopping after the active backend operation...")
        if self._job is not None:
            self._job.cancel()

    def _finish(self, message):
        self._running = False
        self._job = None
        self.timer.stop()
        self.setup_group.setEnabled(True)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText(message)
        if self._close_pending:
            if self._owns_worker:
                self._worker.close()
            self.close()

    def closeEvent(self, event):
        if self._job is not None:
            self._close_pending = True
            self.stop_alignment()
            event.ignore()
            return
        if self._owns_worker:
            self._worker.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = HoribaAlignmentWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
