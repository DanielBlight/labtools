import asyncio
import csv
from pathlib import Path

import pyvisa
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
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
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from labtools.acquisition.range_spectrum import get_range_spectrum
from labtools.devices.horiba_spectrometer import HoribaSpectrometer
from labtools.devices.itc4000 import ITC4000
from labtools.gui.async_runner import AsyncTaskRunner
from labtools.gui.background import apply_background_subtraction, parse_background_csv


class HoribaRangeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Horiba range spectrum")
        self.resize(1150, 820)

        self.spec = None
        self.laser = None
        self.background_spectrum = None
        self._async_tasks = []

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        spectrometer_group = QGroupBox("Horiba spectrometer")
        spectrometer_layout = QFormLayout(spectrometer_group)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["syncerity", "symphony"])
        spectrometer_layout.addRow("Preset", self.preset_combo)

        self.start_wl = QDoubleSpinBox()
        self.start_wl.setRange(0, 2000)
        self.start_wl.setValue(600.0)
        self.start_wl.setDecimals(2)
        spectrometer_layout.addRow("Start wavelength (nm)", self.start_wl)

        self.end_wl = QDoubleSpinBox()
        self.end_wl.setRange(0, 2000)
        self.end_wl.setValue(900.0)
        self.end_wl.setDecimals(2)
        spectrometer_layout.addRow("End wavelength (nm)", self.end_wl)

        self.exposure_box = QDoubleSpinBox()
        self.exposure_box.setRange(0.001, 1000.0)
        self.exposure_box.setSingleStep(0.1)
        self.exposure_box.setValue(0.5)
        self.exposure_box.setDecimals(3)
        spectrometer_layout.addRow("Exposure time (s)", self.exposure_box)

        self.frames_box = QSpinBox()
        self.frames_box.setRange(1, 50)
        self.frames_box.setValue(1)
        spectrometer_layout.addRow("Frames", self.frames_box)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["single", "median", "sigma_clip"])
        spectrometer_layout.addRow("Combine mode", self.mode_combo)

        self.use_background = QCheckBox("Use background subtraction")
        spectrometer_layout.addRow("", self.use_background)

        self.background_mode = QComboBox()
        self.background_mode.addItems(["No background", "Capture dark frame", "Load background CSV"])
        spectrometer_layout.addRow("Background source", self.background_mode)

        self.background_timing = QComboBox()
        self.background_timing.addItems([
            "One dark frame at the start",
            "Dark frame before each repeated acquisition",
        ])
        spectrometer_layout.addRow("Background timing", self.background_timing)

        self.background_status = QLabel("No background selected")
        spectrometer_layout.addRow("", self.background_status)

        self.save_csv = QCheckBox("Save CSV")
        self.save_png = QCheckBox("Save PNG")
        save_row = QHBoxLayout()
        save_row.addWidget(self.save_csv)
        save_row.addWidget(self.save_png)
        spectrometer_layout.addRow("Save output", save_row)

        connect_row = QHBoxLayout()
        self.connect_button = QPushButton("Connect spectrometer")
        self.acquire_button = QPushButton("Acquire range spectrum")
        connect_row.addWidget(self.connect_button)
        connect_row.addWidget(self.acquire_button)
        spectrometer_layout.addRow(connect_row)

        root.addWidget(spectrometer_group)

        laser_group = QGroupBox("Laser control (optional)")
        laser_group.setCheckable(True)
        laser_group.setChecked(False)
        laser_layout = QFormLayout(laser_group)

        self.laser_address = QLineEdit()
        self.laser_address.setText(ITC4000.DEFAULT_ADDRESS)
        laser_layout.addRow("VISA address", self.laser_address)

        self.laser_current = QDoubleSpinBox()
        self.laser_current.setRange(0.0, 2.0)
        self.laser_current.setSingleStep(0.01)
        self.laser_current.setValue(0.08)
        self.laser_current.setDecimals(3)
        laser_layout.addRow("Current (A)", self.laser_current)

        self.laser_light = QLabel("Laser output: OFF")
        self.laser_light.setStyleSheet(
            "QLabel { background-color: #3a3a3a; color: white; border: 1px solid #666; border-radius: 8px; padding: 6px; }"
        )
        laser_layout.addRow("Status", self.laser_light)

        self.laser_connect = QPushButton("Connect laser")
        self.laser_test = QPushButton("Test VISA")
        self.laser_on = QPushButton("Laser ON")
        self.laser_off = QPushButton("Laser OFF")
        self.laser_set = QPushButton("Set current")
        laser_buttons = QHBoxLayout()
        laser_buttons.addWidget(self.laser_connect)
        laser_buttons.addWidget(self.laser_test)
        laser_buttons.addWidget(self.laser_on)
        laser_buttons.addWidget(self.laser_off)
        laser_buttons.addWidget(self.laser_set)
        laser_layout.addRow(laser_buttons)

        root.addWidget(laser_group)

        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.figure = Figure(figsize=(9, 5), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self.figure)
        root.addWidget(self.canvas)

        self.connect_button.clicked.connect(self.connect_spectrometer)
        self.acquire_button.clicked.connect(self.acquire_spectrum)
        self.mode_combo.currentTextChanged.connect(self._update_frame_controls)
        self.background_mode.currentIndexChanged.connect(self._update_background_controls)
        self.use_background.toggled.connect(self._update_background_controls)
        self._update_background_controls()
        self._update_frame_controls()
        laser_group.toggled.connect(self._toggle_laser_controls)
        self.laser_connect.clicked.connect(self.connect_laser)
        self.laser_test.clicked.connect(self.test_laser_connection)
        self.laser_on.clicked.connect(self.turn_laser_on)
        self.laser_off.clicked.connect(self.turn_laser_off)
        self.laser_set.clicked.connect(self.set_laser_current)

    def _toggle_laser_controls(self, enabled):
        self.laser_address.setEnabled(enabled)
        self.laser_current.setEnabled(enabled)
        self.laser_connect.setEnabled(enabled)
        self.laser_test.setEnabled(enabled)
        self.laser_on.setEnabled(enabled and self.laser is not None)
        self.laser_off.setEnabled(enabled and self.laser is not None)
        self.laser_set.setEnabled(enabled and self.laser is not None)

    def _update_background_controls(self):
        enabled = self.use_background.isChecked()
        self.background_mode.setEnabled(enabled)
        mode = self.background_mode.currentText()

        if not enabled:
            self.background_timing.setEnabled(False)
            self.background_status.setText("Background subtraction disabled")
            return

        if mode == "No background":
            self.background_timing.setEnabled(False)
            self.background_status.setText("Select a background source to enable subtraction")
        elif mode == "Capture dark frame":
            self.background_timing.setEnabled(True)
            self.background_status.setText(
                "Dark frame will be captured automatically; choose whether it is taken once or before each repeated acquisition."
            )
        elif mode == "Load background CSV":
            self.background_timing.setEnabled(False)
            self.background_status.setText("Background CSV will be loaded automatically before the scan")

    def _update_frame_controls(self):
        mode = self.mode_combo.currentText()
        minimum = 1 if mode == "single" else 3
        self.frames_box.setMinimum(minimum)
        self.frames_box.setEnabled(mode != "single")
        if self.frames_box.value() < minimum:
            self.frames_box.setValue(minimum)

    def set_status(self, message):
        self.status.setText(message)

    def set_laser_indicator(self, on):
        if on:
            self.laser_light.setText("Laser output: ON")
            self.laser_light.setStyleSheet(
                "QLabel { background-color: #1f5a2a; color: white; border: 1px solid #5fd17a; border-radius: 8px; padding: 6px; }"
            )
        else:
            self.laser_light.setText("Laser output: OFF")
            self.laser_light.setStyleSheet(
                "QLabel { background-color: #3a3a3a; color: white; border: 1px solid #666; border-radius: 8px; padding: 6px; }"
            )

    def _run_async(self, coroutine_factory, on_done, on_error):
        thread = QThread(self)
        runner = AsyncTaskRunner(coroutine_factory)
        runner.moveToThread(thread)
        self._async_tasks.append((thread, runner))

        thread.started.connect(runner.run)
        runner.finished.connect(on_done)
        runner.failed.connect(on_error)
        runner.finished.connect(thread.quit)
        runner.failed.connect(thread.quit)
        runner.finished.connect(runner.deleteLater)
        runner.failed.connect(runner.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def cleanup(_=None):
            if (thread, runner) in self._async_tasks:
                self._async_tasks.remove((thread, runner))

        runner.finished.connect(cleanup)
        runner.failed.connect(cleanup)
        thread.start()

    def connect_spectrometer(self):
        self.set_status("Connecting to spectrometer...")
        self.connect_button.setEnabled(False)
        self.acquire_button.setEnabled(False)

        def task():
            preset = self.preset_combo.currentText()
            exposure = float(self.exposure_box.value())

            async def _connect():
                spec = HoribaSpectrometer(preset=preset)
                await spec.connect()
                await spec.configure(
                    gain=2,
                    speed=0,
                    exposure_time=exposure,
                    roi={},
                )
                return spec

            return _connect

        self._run_async(task(), self._handle_connect_done, self._handle_connect_error)

    def _handle_connect_done(self, spec):
        self.spec = spec
        self.connect_button.setEnabled(True)
        self.acquire_button.setEnabled(True)
        self.set_status(f"Connected to Horiba spectrometer in preset '{self.preset_combo.currentText()}'.")

    def _handle_connect_error(self, error):
        self.connect_button.setEnabled(True)
        self.acquire_button.setEnabled(False)
        self.set_status(f"Spectrometer connection failed: {error}")
        QMessageBox.critical(
            self,
            "Spectrometer connection failed",
            f"Could not connect to the Horiba spectrometer.\n\n{error}\n\nCheck that the device is powered, the USB connection is active, and the preset is correct.",
        )

    def load_background_spectrum(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open background spectrum CSV", str(Path.cwd()), "CSV files (*.csv);;All files (*)")
        if not path:
            return None

        try:
            self.background_spectrum = parse_background_csv(path)
            self.background_status.setText(f"Background loaded from {Path(path).name}")
            self.set_status("Background spectrum loaded.")
            self.background_mode.setCurrentText("Load background CSV")
            return self.background_spectrum
        except Exception as exc:  # pragma: no cover - UI path only
            self.background_status.setText("Background load failed")
            QMessageBox.critical(self, "Background load failed", str(exc))
            return None

    def _apply_background_subtraction(self, x_data, y_data):
        return apply_background_subtraction(x_data, y_data, self.background_spectrum)

    def _dark_frame_mode(self):
        if not self.use_background.isChecked() or self.background_mode.currentText() != "Capture dark frame":
            return "none"
        if self.background_timing.currentText() == "One dark frame at the start":
            return "single"
        return "per_frame"

    def _uses_loaded_background(self):
        return self.use_background.isChecked() and self.background_mode.currentText() == "Load background CSV"

    def acquire_spectrum(self):
        if self.spec is None:
            QMessageBox.warning(self, "Not connected", "Connect to the spectrometer before acquiring.")
            return

        if self.use_background.isChecked():
            mode = self.background_mode.currentText()
            if mode == "No background":
                QMessageBox.warning(self, "No background selected", "Choose a background source before enabling background subtraction.")
                return
            if mode == "Capture dark frame":
                self.background_spectrum = None
                self.set_status("Dark frames will be captured automatically during acquisition.")
            elif mode == "Load background CSV":
                loaded = self.load_background_spectrum()
                if loaded is None:
                    return
                self.background_spectrum = loaded

        start = float(self.start_wl.value())
        end = float(self.end_wl.value())
        if end < start:
            start, end = end, start
            self.start_wl.setValue(start)
            self.end_wl.setValue(end)

        self.set_status(f"Acquiring spectrum {start:.2f}–{end:.2f} nm...")
        self.acquire_button.setEnabled(False)
        background_mode = self.background_mode.currentText()
        background_subtract = self.use_background.isChecked() and background_mode == "Capture dark frame"
        dark_frame_mode = self._dark_frame_mode() if background_subtract else "none"

        def task():
            async def _acquire():
                return await get_range_spectrum(
                    self.spec,
                    start,
                    end,
                    n_frames=int(self.frames_box.value()),
                    mode=self.mode_combo.currentText(),
                    background_subtract=background_subtract,
                    dark_frame_mode=dark_frame_mode,
                )

            return _acquire

        self._run_async(task(), self._handle_acquire_done, self._handle_acquire_error)

    def _handle_acquire_done(self, result):
        self.acquire_button.setEnabled(True)
        x_data, y_data = result

        try:
            if self._uses_loaded_background():
                y_data = self._apply_background_subtraction(x_data, y_data)
        except Exception as exc:
            self.set_status(f"Background subtraction failed: {exc}")
            QMessageBox.critical(self, "Background subtraction failed", str(exc))
            return

        self.ax.clear()
        self.ax.plot(x_data, y_data, color="tab:blue")
        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("Intensity")
        self.ax.set_title("Horiba spectrum")
        self.ax.grid(True, alpha=0.3)
        self.figure.tight_layout()
        self.canvas.draw_idle()

        self._maybe_save_result(x_data, y_data)

        self.set_status("Spectrum acquired successfully.")

    def _handle_acquire_error(self, error):
        self.acquire_button.setEnabled(True)
        self.set_status(f"Acquisition failed: {error}")
        QMessageBox.critical(self, "Acquisition failed", error)

    def _maybe_save_result(self, x_data, y_data):
        if not (self.save_csv.isChecked() or self.save_png.isChecked()):
            return

        output_dir = Path.cwd() / "spectra"
        output_dir.mkdir(exist_ok=True)

        stem = f"horiba_{float(self.start_wl.value()):.0f}_{float(self.end_wl.value()):.0f}nm"
        if self.save_csv.isChecked():
            csv_path = output_dir / f"{stem}.csv"
            with open(csv_path, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["wavelength_nm", "intensity"])
                for wl, intensity in zip(x_data, y_data):
                    writer.writerow([float(wl), float(intensity)])

        if self.save_png.isChecked():
            png_path = output_dir / f"{stem}.png"
            self.figure.savefig(png_path, dpi=200)

    def test_laser_connection(self):
        address = self.laser_address.text().strip() or ITC4000.DEFAULT_ADDRESS
        self.laser_test.setEnabled(False)
        self.set_status(f"Testing VISA connection to {address}...")

        try:
            resource_manager = pyvisa.ResourceManager()
            try:
                instrument = resource_manager.open_resource(address, timeout=2000)
                try:
                    idn = instrument.query("*IDN?").strip()
                finally:
                    instrument.close()
            finally:
                resource_manager.close()
            self.set_status(f"VISA connection OK: {address} -> {idn}")
            QMessageBox.information(self, "VISA connection OK", f"Address: {address}\n\nIDN: {idn}")
        except Exception as exc:
            self.set_status(f"VISA test failed for {address}: {exc}")
            QMessageBox.critical(
                self,
                "VISA test failed",
                f"Could not communicate with the ITC4000 at {address}.\n\n{exc}\n\nCheck the USB connection, device power, and VISA address.",
            )
        finally:
            self.laser_test.setEnabled(True)

    def connect_laser(self):
        address = self.laser_address.text().strip() or ITC4000.DEFAULT_ADDRESS
        self.set_status(f"Connecting to laser at {address}...")
        self.laser_connect.setEnabled(False)

        def task():
            async def _connect():
                return ITC4000(address)

            return _connect

        self._run_async(task(), self._handle_laser_connected, self._handle_laser_error)

    def _handle_laser_connected(self, laser):
        self.laser = laser
        self.laser_connect.setEnabled(True)
        self.laser_test.setEnabled(True)
        self.laser_on.setEnabled(True)
        self.laser_off.setEnabled(True)
        self.laser_set.setEnabled(True)
        self.set_laser_indicator(False)
        self.set_status(f"Connected to ITC4000 at {self.laser_address.text().strip()}.")

    def _handle_laser_error(self, error):
        self.laser = None
        self.laser_on.setEnabled(False)
        self.laser_off.setEnabled(False)
        self.laser_set.setEnabled(False)
        self.laser_connect.setEnabled(True)
        self.set_laser_indicator(False)
        self.set_status(f"Laser connection failed: {error}")
        QMessageBox.critical(
            self,
            "Laser connection failed",
            f"Could not connect to the ITC4000 laser controller at {self.laser_address.text().strip() or ITC4000.DEFAULT_ADDRESS}.\n\n{error}\n\nCheck that the device is powered on, connected over USB, and that the VISA address is correct.",
        )

    def turn_laser_on(self):
        if self.laser is None:
            QMessageBox.warning(self, "No laser", "Connect the laser first.")
            return

        current = float(self.laser_current.value())
        self.set_status(f"Turning laser on at {current:.3f} A...")
        try:
            self.laser.enable(current=current)
            self.set_laser_indicator(True)
            self.set_status(f"Laser enabled at {current:.3f} A.")
        except Exception as exc:  # pragma: no cover - UI path only
            self.set_status(f"Laser enable failed: {exc}")
            QMessageBox.critical(self, "Laser enable failed", str(exc))

    def turn_laser_off(self):
        if self.laser is None:
            QMessageBox.warning(self, "No laser", "Connect the laser first.")
            return

        self.set_status("Turning laser off...")
        try:
            self.laser.disable()
            self.set_laser_indicator(False)
            self.set_status("Laser off.")
        except Exception as exc:  # pragma: no cover - UI path only
            self.set_status(f"Laser shutdown failed: {exc}")
            QMessageBox.critical(self, "Laser shutdown failed", str(exc))

    def set_laser_current(self):
        if self.laser is None:
            QMessageBox.warning(self, "No laser", "Connect the laser first.")
            return

        current = float(self.laser_current.value())
        self.set_status(f"Setting laser current to {current:.3f} A...")
        try:
            self.laser.set_current(current)
            self.set_status(f"Laser current set to {current:.3f} A.")
        except Exception as exc:  # pragma: no cover - UI path only
            self.set_status(f"Set current failed: {exc}")
            QMessageBox.critical(self, "Set current failed", str(exc))

    def closeEvent(self, event):
        try:
            if self.laser is not None:
                self.laser.disable()
                self.laser.close()
        except Exception:
            pass
        try:
            if self.spec is not None:
                asyncio.run(self.spec.disconnect())
        except Exception:
            pass
        super().closeEvent(event)


def main():
    import sys

    app = QApplication(sys.argv)
    window = HoribaRangeWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
