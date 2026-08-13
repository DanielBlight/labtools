import asyncio
import csv
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
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

from horiba_sdk.core.stitching import LinearSpectraStitch

from labtools.acquisition.range_spectrum import get_range_spectrum
from labtools.devices.horiba_spectrometer import HoribaSpectrometer
from labtools.devices.itc4000 import ITC4000


class AsyncTaskRunner(QObject):
    """Run an async coroutine in a worker thread and forward the result to the UI thread."""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, coroutine_factory):
        super().__init__()
        self.coroutine_factory = coroutine_factory

    @pyqtSlot()
    def run(self):
        try:
            result = asyncio.run(self.coroutine_factory())
        except Exception as exc:  # pragma: no cover - UI path only
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)


class HoribaRangeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Horiba range spectrum")
        self.resize(1150, 820)

        self.spec = None
        self.laser = None
        self.background_spectrum = None

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
        self.laser_on = QPushButton("Laser ON")
        self.laser_off = QPushButton("Laser OFF")
        self.laser_set = QPushButton("Set current")
        laser_buttons = QHBoxLayout()
        laser_buttons.addWidget(self.laser_connect)
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
        self.background_mode.currentIndexChanged.connect(self._update_background_controls)
        self.use_background.toggled.connect(self._update_background_controls)
        self._update_background_controls()
        laser_group.toggled.connect(self._toggle_laser_controls)
        self.laser_connect.clicked.connect(self.connect_laser)
        self.laser_on.clicked.connect(self.turn_laser_on)
        self.laser_off.clicked.connect(self.turn_laser_off)
        self.laser_set.clicked.connect(self.set_laser_current)

    def _toggle_laser_controls(self, enabled):
        self.laser_address.setEnabled(enabled)
        self.laser_current.setEnabled(enabled)
        self.laser_connect.setEnabled(enabled)
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
        thread.started.connect(runner.run)
        runner.finished.connect(on_done)
        runner.failed.connect(on_error)
        runner.finished.connect(thread.quit)
        runner.failed.connect(thread.quit)
        runner.finished.connect(runner.deleteLater)
        runner.failed.connect(runner.deleteLater)
        thread.finished.connect(thread.deleteLater)
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
        QMessageBox.critical(self, "Connection failed", error)

    async def _capture_background_frame(self):
        if self.spec is None:
            raise RuntimeError("Connect to the spectrometer before capturing a dark frame.")

        exposure_time = float(self.exposure_box.value())
        await self.spec.ccd.acquisition_start(open_shutter=False)
        await asyncio.sleep(exposure_time + 0.005)
        while await self.spec.ccd.get_acquisition_busy():
            await asyncio.sleep(0.002)
        raw = await self.spec.ccd.get_acquisition_data()
        x_data = raw["acquisition"][0]["roi"][0]["xData"]
        y_data = raw["acquisition"][0]["roi"][0]["yData"][0]
        return np.asarray(x_data), np.asarray(y_data)

    def capture_background(self):
        self.set_status("Capturing dark background frame...")
        return self._capture_background_frame

    def _handle_background_captured(self, result):
        x_data, y_data = result
        self.background_spectrum = (np.asarray(x_data), np.asarray(y_data))
        self.background_status.setText("Background captured from dark frame")
        self.set_status("Dark frame captured successfully.")
        self.background_mode.setCurrentText("Capture dark frame")

    def _handle_background_capture_error(self, error):
        self.set_status(f"Dark frame capture failed: {error}")
        QMessageBox.critical(self, "Dark frame failed", error)

    def load_background_spectrum(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open background spectrum CSV", str(Path.cwd()), "CSV files (*.csv);;All files (*)")
        if not path:
            return None

        try:
            with open(path, newline="") as fh:
                rows = [row for row in csv.reader(fh) if row and not all(cell.strip() == "" for cell in row)]
            if not rows:
                raise ValueError("Background CSV is empty.")

            data = []
            start_index = 0
            if len(rows[0]) >= 2 and rows[0][0].strip().lower() in {"wavelength", "wl", "x", "x_data"}:
                start_index = 1
            for row in rows[start_index:]:
                if len(row) < 2:
                    continue
                data.append((float(row[0]), float(row[1])))
            if not data:
                raise ValueError("Background CSV does not contain wavelength, intensity pairs.")

            x_vals, y_vals = zip(*data)
            self.background_spectrum = (np.asarray(x_vals, dtype=float), np.asarray(y_vals, dtype=float))
            self.background_status.setText(f"Background loaded from {Path(path).name}")
            self.set_status("Background spectrum loaded.")
            self.background_mode.setCurrentText("Load background CSV")
            return self.background_spectrum
        except Exception as exc:  # pragma: no cover - UI path only
            self.background_status.setText("Background load failed")
            QMessageBox.critical(self, "Background load failed", str(exc))
            return None

    def _apply_background_subtraction(self, x_data, y_data):
        if self.background_spectrum is None:
            raise ValueError("No background spectrum available. Capture a dark frame or load a background CSV first.")

        bg_x, bg_y = self.background_spectrum
        x_arr = np.asarray(x_data)
        if bg_x.shape != x_arr.shape or not np.allclose(bg_x, x_arr, rtol=0, atol=1e-8):
            raise ValueError("Background wavelength values must be identical to the acquired spectrum wavelength values.")

        return np.asarray(y_data, dtype=float) - np.asarray(bg_y, dtype=float)

    def _use_per_step_background(self):
        return (
            self.use_background.isChecked()
            and self.background_mode.currentText() == "Capture dark frame"
            and self.background_timing.currentText() == "Dark frame before each repeated acquisition"
        )

    def _dark_frame_mode(self):
        if not self.use_background.isChecked() or self.background_mode.currentText() != "Capture dark frame":
            return "none"
        if self.background_timing.currentText() == "One dark frame at the start":
            return "single"
        return "per_frame"

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
                if self.background_timing.currentText() == "One dark frame at the start":
                    try:
                        self.set_status("Capturing dark background frame...")
                        self.background_spectrum = asyncio.run(self.capture_background()())
                        self._handle_background_captured(self.background_spectrum)
                    except Exception as exc:
                        self._handle_background_capture_error(str(exc))
                        return
                else:
                    self.background_spectrum = None
                    self.set_status("Dark frames will be captured automatically before each repeated acquisition.")
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

        def task():
            async def _acquire():
                background_subtract = self.use_background.isChecked() and self.background_mode.currentText() == "Capture dark frame" and self._use_per_step_background()
                return await get_range_spectrum(
                    self.spec,
                    start,
                    end,
                    n_frames=int(self.frames_box.value()),
                    mode=self.mode_combo.currentText(),
                    background_subtract=background_subtract,
                    dark_frame_mode=self._dark_frame_mode() if background_subtract else "none",
                )

            return _acquire

        self._run_async(task(), self._handle_acquire_done, self._handle_acquire_error)

    def _handle_acquire_done(self, result):
        self.acquire_button.setEnabled(True)
        x_data, y_data = result

        try:
            if self.use_background.isChecked() and not self._use_per_step_background():
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
        self.laser_on.setEnabled(True)
        self.laser_off.setEnabled(True)
        self.laser_set.setEnabled(True)
        self.set_laser_indicator(False)
        self.set_status(f"Connected to ITC4000 at {self.laser_address.text().strip()}.")

    def _handle_laser_error(self, error):
        self.laser_connect.setEnabled(True)
        self.set_status(f"Laser connection failed: {error}")
        QMessageBox.critical(self, "Laser connection failed", error)

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
