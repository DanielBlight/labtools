"""GUI for HORIBA range spectra and optional ITC4000 laser control.

The HORIBA spectrometer operations use asynchronous worker threads because
the HORIBA SDK exposes asynchronous methods.

The ITC4000 PyVISA connection remains in the GUI thread for its complete
lifetime. Connection validation, identification, readback, and control all
use the same persistent VISA session.
"""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import Any, Callable, Coroutine

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
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
)
from matplotlib.figure import Figure

from labtools.acquisition.range_spectrum import (
    get_range_spectrum,
)
from labtools.devices.horiba_spectrometer import (
    HoribaSpectrometer,
)
from labtools.devices.itc4000 import ITC4000
from labtools.gui.async_runner import AsyncTaskRunner
from labtools.gui.background import (
    apply_background_subtraction,
    parse_background_csv,
)


# ----------------------------------------------------------------------
# Laser configuration
# ----------------------------------------------------------------------
# Set this to the documented, lab-approved limit for the connected diode.
# The GUI and ITC4000 wrapper both reject higher values.
MAX_LASER_CURRENT_A = 0.100

# Initial value displayed by the GUI.
DEFAULT_LASER_CURRENT_A = 0.080

# Setpoint applied after the laser-diode output has been disabled.
LASER_THRESHOLD_CURRENT_A = 0.049


class HoribaRangeWindow(QMainWindow):
    """Main window for HORIBA spectra and optional ITC4000 control."""

    def __init__(self) -> None:
        """Build the interface and initialise disconnected device state."""
        super().__init__()

        self.setWindowTitle("Horiba range spectrum")
        self.resize(1150, 820)

        self.spec: HoribaSpectrometer | None = None
        self.laser: ITC4000 | None = None
        self.background_spectrum: Any = None

        # Keep references to worker objects so that Qt does not destroy
        # them while asynchronous spectrometer work is still running.
        self._async_tasks: list[
            tuple[QThread, AsyncTaskRunner]
        ] = []

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        self._build_spectrometer_controls(root)
        self._build_laser_controls(root)

        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.figure = Figure(
            figsize=(9, 5),
            dpi=100,
        )
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self.figure)
        root.addWidget(self.canvas)

        self._connect_signals()
        self._update_background_controls()
        self._update_frame_controls()
        self._toggle_laser_controls(
            self.laser_group.isChecked()
        )

    # ------------------------------------------------------------------
    # Interface construction
    # ------------------------------------------------------------------
    def _build_spectrometer_controls(
        self,
        root: QVBoxLayout,
    ) -> None:
        """Create the HORIBA acquisition controls."""
        group = QGroupBox("Horiba spectrometer")
        layout = QFormLayout(group)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(
            ["syncerity", "symphony"]
        )
        layout.addRow(
            "Preset",
            self.preset_combo,
        )

        self.start_wl = QDoubleSpinBox()
        self.start_wl.setRange(0, 2000)
        self.start_wl.setValue(600.0)
        self.start_wl.setDecimals(2)
        layout.addRow(
            "Start wavelength (nm)",
            self.start_wl,
        )

        self.end_wl = QDoubleSpinBox()
        self.end_wl.setRange(0, 2000)
        self.end_wl.setValue(900.0)
        self.end_wl.setDecimals(2)
        layout.addRow(
            "End wavelength (nm)",
            self.end_wl,
        )

        self.exposure_box = QDoubleSpinBox()
        self.exposure_box.setRange(
            0.001,
            1000.0,
        )
        self.exposure_box.setSingleStep(0.1)
        self.exposure_box.setValue(0.5)
        self.exposure_box.setDecimals(3)
        layout.addRow(
            "Exposure time (s)",
            self.exposure_box,
        )

        self.frames_box = QSpinBox()
        self.frames_box.setRange(1, 50)
        self.frames_box.setValue(1)
        layout.addRow(
            "Frames",
            self.frames_box,
        )

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            ["single", "median", "sigma_clip"]
        )
        layout.addRow(
            "Combine mode",
            self.mode_combo,
        )

        self.use_background = QCheckBox(
            "Use background subtraction"
        )
        layout.addRow(
            "",
            self.use_background,
        )

        self.background_mode = QComboBox()
        self.background_mode.addItems(
            [
                "No background",
                "Capture dark frame",
                "Load background CSV",
            ]
        )
        layout.addRow(
            "Background source",
            self.background_mode,
        )

        self.background_timing = QComboBox()
        self.background_timing.addItems(
            [
                "One dark frame at the start",
                "Dark frame before each repeated acquisition",
            ]
        )
        layout.addRow(
            "Background timing",
            self.background_timing,
        )

        self.background_status = QLabel(
            "No background selected"
        )
        layout.addRow(
            "",
            self.background_status,
        )

        self.save_csv = QCheckBox("Save CSV")
        self.save_png = QCheckBox("Save PNG")

        save_row = QHBoxLayout()
        save_row.addWidget(self.save_csv)
        save_row.addWidget(self.save_png)

        layout.addRow(
            "Save output",
            save_row,
        )

        self.connect_button = QPushButton(
            "Connect spectrometer"
        )
        self.acquire_button = QPushButton(
            "Acquire range spectrum"
        )

        connect_row = QHBoxLayout()
        connect_row.addWidget(self.connect_button)
        connect_row.addWidget(self.acquire_button)

        layout.addRow(connect_row)
        root.addWidget(group)

    def _build_laser_controls(
        self,
        root: QVBoxLayout,
    ) -> None:
        """Create ITC4000 controls.

        No separate VISA test button is created. The persistent session is
        validated automatically when **Connect laser** is selected.
        """
        self.laser_group = QGroupBox(
            "Laser control (optional)"
        )
        self.laser_group.setCheckable(True)
        self.laser_group.setChecked(False)

        layout = QFormLayout(self.laser_group)

        self.laser_address = QLineEdit()
        self.laser_address.setText(
            ITC4000.DEFAULT_ADDRESS
        )
        layout.addRow(
            "VISA address",
            self.laser_address,
        )

        self.laser_current = QDoubleSpinBox()
        self.laser_current.setRange(
            0.0,
            MAX_LASER_CURRENT_A,
        )
        self.laser_current.setSingleStep(0.001)
        self.laser_current.setValue(
            DEFAULT_LASER_CURRENT_A
        )
        self.laser_current.setDecimals(3)
        layout.addRow(
            "Current (A)",
            self.laser_current,
        )

        self.laser_light = QLabel(
            "Laser output: OFF"
        )
        self.set_laser_indicator(False)
        layout.addRow(
            "Status",
            self.laser_light,
        )

        self.laser_connect = QPushButton(
            "Connect laser"
        )
        self.laser_on = QPushButton(
            "Laser ON"
        )
        self.laser_off = QPushButton(
            "Laser OFF"
        )
        self.laser_set = QPushButton(
            "Set current"
        )

        button_row = QHBoxLayout()
        button_row.addWidget(self.laser_connect)
        button_row.addWidget(self.laser_on)
        button_row.addWidget(self.laser_off)
        button_row.addWidget(self.laser_set)

        layout.addRow(button_row)
        root.addWidget(self.laser_group)

    def _connect_signals(self) -> None:
        """Connect widgets to their handlers."""
        self.connect_button.clicked.connect(
            self.connect_spectrometer
        )
        self.acquire_button.clicked.connect(
            self.acquire_spectrum
        )

        self.mode_combo.currentTextChanged.connect(
            self._update_frame_controls
        )

        self.background_mode.currentIndexChanged.connect(
            self._update_background_controls
        )
        self.use_background.toggled.connect(
            self._update_background_controls
        )

        self.laser_group.toggled.connect(
            self._toggle_laser_controls
        )
        self.laser_connect.clicked.connect(
            self.connect_laser
        )
        self.laser_on.clicked.connect(
            self.turn_laser_on
        )
        self.laser_off.clicked.connect(
            self.turn_laser_off
        )
        self.laser_set.clicked.connect(
            self.set_laser_current
        )

    # ------------------------------------------------------------------
    # General UI state
    # ------------------------------------------------------------------
    def set_status(self, message: str) -> None:
        """Display a status message below the controls."""
        self.status.setText(message)

    def set_laser_indicator(self, on: bool) -> None:
        """Update the laser-output indicator from controller readback."""
        if on:
            self.laser_light.setText(
                "Laser output: ON"
            )
            self.laser_light.setStyleSheet(
                "QLabel { "
                "background-color: #1f5a2a; "
                "color: white; "
                "border: 1px solid #5fd17a; "
                "border-radius: 8px; "
                "padding: 6px; "
                "}"
            )
        else:
            self.laser_light.setText(
                "Laser output: OFF"
            )
            self.laser_light.setStyleSheet(
                "QLabel { "
                "background-color: #3a3a3a; "
                "color: white; "
                "border: 1px solid #666; "
                "border-radius: 8px; "
                "padding: 6px; "
                "}"
            )

    def _toggle_laser_controls(
        self,
        enabled: bool,
    ) -> None:
        """Enable controls only when optional laser control is selected."""
        connected = self.laser is not None

        self.laser_address.setEnabled(
            enabled and not connected
        )
        self.laser_current.setEnabled(enabled)
        self.laser_connect.setEnabled(enabled)
        self.laser_on.setEnabled(
            enabled and connected
        )
        self.laser_off.setEnabled(
            enabled and connected
        )
        self.laser_set.setEnabled(
            enabled and connected
        )

    def _update_background_controls(self) -> None:
        """Enable controls relevant to the selected background mode."""
        enabled = self.use_background.isChecked()
        mode = self.background_mode.currentText()

        self.background_mode.setEnabled(enabled)

        if not enabled:
            self.background_timing.setEnabled(False)
            self.background_status.setText(
                "Background subtraction disabled"
            )

        elif mode == "No background":
            self.background_timing.setEnabled(False)
            self.background_status.setText(
                "Select a background source to enable subtraction"
            )

        elif mode == "Capture dark frame":
            self.background_timing.setEnabled(True)
            self.background_status.setText(
                "Dark frames will be captured automatically "
                "during acquisition."
            )

        else:
            self.background_timing.setEnabled(False)
            self.background_status.setText(
                "A background CSV will be loaded "
                "before acquisition."
            )

    def _update_frame_controls(self) -> None:
        """Enforce the frame count needed by the combine mode."""
        mode = self.mode_combo.currentText()
        minimum = 1 if mode == "single" else 3

        self.frames_box.setMinimum(minimum)
        self.frames_box.setEnabled(
            mode != "single"
        )

        if self.frames_box.value() < minimum:
            self.frames_box.setValue(minimum)

    # ------------------------------------------------------------------
    # Async HORIBA helper
    # ------------------------------------------------------------------
    def _run_async(
        self,
        coroutine_factory: Callable[
            [],
            Coroutine[Any, Any, Any],
        ],
        on_done: Callable[[Any], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Run an async HORIBA operation outside the Qt event loop."""
        thread = QThread(self)
        runner = AsyncTaskRunner(
            coroutine_factory
        )

        runner.moveToThread(thread)
        self._async_tasks.append(
            (thread, runner)
        )

        thread.started.connect(runner.run)
        runner.finished.connect(on_done)
        runner.failed.connect(on_error)

        runner.finished.connect(thread.quit)
        runner.failed.connect(thread.quit)

        runner.finished.connect(
            runner.deleteLater
        )
        runner.failed.connect(
            runner.deleteLater
        )
        thread.finished.connect(
            thread.deleteLater
        )

        def cleanup(
            _: object = None,
        ) -> None:
            """Remove completed Qt worker references."""
            task = (thread, runner)

            if task in self._async_tasks:
                self._async_tasks.remove(task)

        runner.finished.connect(cleanup)
        runner.failed.connect(cleanup)

        thread.start()

    # ------------------------------------------------------------------
    # HORIBA spectrometer
    # ------------------------------------------------------------------
    def connect_spectrometer(self) -> None:
        """Connect to and configure the selected HORIBA preset."""
        self.set_status(
            "Connecting to spectrometer..."
        )

        self.connect_button.setEnabled(False)
        self.acquire_button.setEnabled(False)

        preset = self.preset_combo.currentText()
        exposure = float(
            self.exposure_box.value()
        )

        async def connect() -> HoribaSpectrometer:
            """Open and configure the HORIBA SDK connection."""
            spec = HoribaSpectrometer(
                preset=preset
            )

            await spec.connect()

            await spec.configure(
                gain=2,
                speed=0,
                exposure_time=exposure,
                roi={},
            )

            return spec

        self._run_async(
            lambda: connect(),
            self._handle_connect_done,
            self._handle_connect_error,
        )

    def _handle_connect_done(
        self,
        spec: HoribaSpectrometer,
    ) -> None:
        """Store a connected spectrometer returned by the worker."""
        self.spec = spec

        self.connect_button.setEnabled(True)
        self.acquire_button.setEnabled(True)

        self.set_status(
            "Connected to HORIBA spectrometer in preset "
            f"'{self.preset_combo.currentText()}'."
        )

    def _handle_connect_error(
        self,
        error: str,
    ) -> None:
        """Report a spectrometer connection failure."""
        self.connect_button.setEnabled(True)
        self.acquire_button.setEnabled(False)

        self.set_status(
            f"Spectrometer connection failed: {error}"
        )

        QMessageBox.critical(
            self,
            "Spectrometer connection failed",
            (
                "Could not connect to the HORIBA spectrometer.\n\n"
                f"{error}\n\n"
                "Check device power, USB connection, ICL, "
                "and detector preset."
            ),
        )

    def load_background_spectrum(
        self,
    ) -> Any | None:
        """Prompt for and parse a background-spectrum CSV file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open background spectrum CSV",
            str(Path.cwd()),
            "CSV files (*.csv);;All files (*)",
        )

        if not path:
            return None

        try:
            self.background_spectrum = (
                parse_background_csv(path)
            )

            self.background_status.setText(
                f"Background loaded from "
                f"{Path(path).name}"
            )

            self.set_status(
                "Background spectrum loaded."
            )

            self.background_mode.setCurrentText(
                "Load background CSV"
            )

            return self.background_spectrum

        except Exception as exc:
            self.background_status.setText(
                "Background load failed"
            )

            QMessageBox.critical(
                self,
                "Background load failed",
                str(exc),
            )

            return None

    def _apply_background_subtraction(
        self,
        x_data: Any,
        y_data: Any,
    ) -> Any:
        """Subtract the currently loaded background spectrum."""
        return apply_background_subtraction(
            x_data,
            y_data,
            self.background_spectrum,
        )

    def _dark_frame_mode(self) -> str:
        """Translate the selected timing into an acquisition mode."""
        if (
            not self.use_background.isChecked()
            or self.background_mode.currentText()
            != "Capture dark frame"
        ):
            return "none"

        if (
            self.background_timing.currentText()
            == "One dark frame at the start"
        ):
            return "single"

        return "per_frame"

    def _uses_loaded_background(self) -> bool:
        """Return whether subtraction should use a loaded CSV."""
        return (
            self.use_background.isChecked()
            and self.background_mode.currentText()
            == "Load background CSV"
        )

    def acquire_spectrum(self) -> None:
        """Acquire a stitched spectrum using current UI settings."""
        if self.spec is None:
            QMessageBox.warning(
                self,
                "Not connected",
                "Connect to the spectrometer before acquiring.",
            )
            return

        if self.use_background.isChecked():
            background_mode = (
                self.background_mode.currentText()
            )

            if background_mode == "No background":
                QMessageBox.warning(
                    self,
                    "No background selected",
                    (
                        "Choose a background source before "
                        "enabling subtraction."
                    ),
                )
                return

            if background_mode == "Capture dark frame":
                self.background_spectrum = None
                self.set_status(
                    "Dark frames will be captured automatically "
                    "during acquisition."
                )

            elif self.load_background_spectrum() is None:
                return

        start = float(
            self.start_wl.value()
        )
        end = float(
            self.end_wl.value()
        )

        if end < start:
            start, end = end, start

            self.start_wl.setValue(start)
            self.end_wl.setValue(end)

        self.set_status(
            f"Acquiring spectrum "
            f"{start:.2f}-{end:.2f} nm..."
        )

        self.acquire_button.setEnabled(False)

        background_subtract = (
            self.use_background.isChecked()
            and self.background_mode.currentText()
            == "Capture dark frame"
        )

        dark_frame_mode = (
            self._dark_frame_mode()
            if background_subtract
            else "none"
        )

        n_frames = int(
            self.frames_box.value()
        )

        combine_mode = (
            self.mode_combo.currentText()
        )

        async def acquire() -> tuple[Any, Any]:
            """Acquire one stitched range spectrum."""
            return await get_range_spectrum(
                self.spec,
                start,
                end,
                n_frames=n_frames,
                mode=combine_mode,
                background_subtract=background_subtract,
                dark_frame_mode=dark_frame_mode,
            )

        self._run_async(
            lambda: acquire(),
            self._handle_acquire_done,
            self._handle_acquire_error,
        )

    def _handle_acquire_done(
        self,
        result: tuple[Any, Any],
    ) -> None:
        """Plot and optionally save a completed spectrum."""
        self.acquire_button.setEnabled(True)

        x_data, y_data = result

        try:
            if self._uses_loaded_background():
                y_data = (
                    self._apply_background_subtraction(
                        x_data,
                        y_data,
                    )
                )

        except Exception as exc:
            self.set_status(
                f"Background subtraction failed: {exc}"
            )

            QMessageBox.critical(
                self,
                "Background subtraction failed",
                str(exc),
            )

            return

        self.ax.clear()

        self.ax.plot(
            x_data,
            y_data,
            color="tab:blue",
        )

        self.ax.set_xlabel(
            "Wavelength (nm)"
        )
        self.ax.set_ylabel(
            "Intensity"
        )
        self.ax.set_title(
            "HORIBA spectrum"
        )
        self.ax.grid(
            True,
            alpha=0.3,
        )

        self.figure.tight_layout()
        self.canvas.draw_idle()

        self._maybe_save_result(
            x_data,
            y_data,
        )

        self.set_status(
            "Spectrum acquired successfully."
        )

    def _handle_acquire_error(
        self,
        error: str,
    ) -> None:
        """Report a failed range acquisition."""
        self.acquire_button.setEnabled(True)

        self.set_status(
            f"Acquisition failed: {error}"
        )

        QMessageBox.critical(
            self,
            "Acquisition failed",
            error,
        )

    def _maybe_save_result(
        self,
        x_data: Any,
        y_data: Any,
    ) -> None:
        """Save selected CSV and PNG output files."""
        if not (
            self.save_csv.isChecked()
            or self.save_png.isChecked()
        ):
            return

        output_dir = (
            Path.cwd() / "spectra"
        )
        output_dir.mkdir(
            exist_ok=True
        )

        stem = (
            f"horiba_"
            f"{float(self.start_wl.value()):.0f}_"
            f"{float(self.end_wl.value()):.0f}nm"
        )

        if self.save_csv.isChecked():
            csv_path = (
                output_dir / f"{stem}.csv"
            )

            with csv_path.open(
                "w",
                newline="",
            ) as handle:
                writer = csv.writer(handle)

                writer.writerow(
                    [
                        "wavelength_nm",
                        "intensity",
                    ]
                )

                for wavelength, intensity in zip(
                    x_data,
                    y_data,
                ):
                    writer.writerow(
                        [
                            float(wavelength),
                            float(intensity),
                        ]
                    )

        if self.save_png.isChecked():
            png_path = (
                output_dir / f"{stem}.png"
            )

            self.figure.savefig(
                png_path,
                dpi=200,
            )

    # ------------------------------------------------------------------
    # ITC4000 laser control
    # ------------------------------------------------------------------
    def connect_laser(self) -> None:
        """Connect, query identity/state, and retain the live session.

        The following operations are performed using the same session that
        will later receive the output and setpoint commands:

        1. Open the VISA resource.
        2. Query ``*IDN?``.
        3. Query the laser-current setpoint.
        4. Query laser-diode output state.
        5. Query TEC output state.
        6. Retain the connection if all queries succeed.
        """
        address = (
            self.laser_address.text().strip()
            or ITC4000.DEFAULT_ADDRESS
        )

        self.set_status(
            f"Connecting to laser at {address}..."
        )

        self.laser_connect.setEnabled(False)

        try:
            # Explicitly close an earlier connection before reconnecting.
            if self.laser is not None:
                self.laser.close()
                self.laser = None

            laser = ITC4000(
                address,
                threshold_current=(
                    LASER_THRESHOLD_CURRENT_A
                ),
                max_current=MAX_LASER_CURRENT_A,
            )

            # Validate the exact persistent session that the GUI will use.
            try:
                identity = laser.identify()
                current = laser.get_current()
                diode_on = (
                    laser.get_diode_output()
                )
                tec_on = (
                    laser.get_tec_output()
                )

            except Exception:
                laser.close()
                raise

            self.laser = laser

            self.laser_address.setEnabled(False)
            self.laser_on.setEnabled(True)
            self.laser_off.setEnabled(True)
            self.laser_set.setEnabled(True)

            # Display the real controller setpoint rather than retaining
            # a potentially stale value from the GUI.
            self.laser_current.setValue(
                current
            )

            self.set_laser_indicator(
                diode_on
            )

            diode_text = (
                "ON" if diode_on else "OFF"
            )
            tec_text = (
                "ON" if tec_on else "OFF"
            )

            self.set_status(
                f"Connected: {identity} | "
                f"Current: {current:.3f} A | "
                f"LD: {diode_text} | "
                f"TEC: {tec_text}"
            )

        except Exception as exc:
            self.laser = None

            self.laser_address.setEnabled(True)
            self.laser_on.setEnabled(False)
            self.laser_off.setEnabled(False)
            self.laser_set.setEnabled(False)

            self.set_laser_indicator(False)

            self.set_status(
                f"Laser connection failed: {exc}"
            )

            QMessageBox.critical(
                self,
                "Laser connection failed",
                (
                    f"Could not connect to the ITC4000 "
                    f"at {address}.\n\n{exc}"
                ),
            )

        finally:
            self.laser_connect.setEnabled(True)

    def turn_laser_on(self) -> None:
        """Apply the selected current and enable diode output."""
        if self.laser is None:
            QMessageBox.warning(
                self,
                "No laser",
                "Connect the laser first.",
            )
            return

        current = float(
            self.laser_current.value()
        )

        self.set_status(
            f"Turning laser on at {current:.3f} A..."
        )

        # Make the status update visible before any TEC stabilisation delay.
        QApplication.processEvents()

        try:
            self.laser.enable(
                current=current
            )

            diode_on = (
                self.laser.get_diode_output()
            )
            current_readback = (
                self.laser.get_current()
            )

            self.set_laser_indicator(
                diode_on
            )

            output_text = (
                "ON" if diode_on else "OFF"
            )

            self.set_status(
                f"Laser output confirmed {output_text}; "
                f"current setpoint "
                f"{current_readback:.3f} A."
            )

        except Exception as exc:
            self.set_laser_indicator(False)

            self.set_status(
                f"Laser enable failed: {exc}"
            )

            QMessageBox.critical(
                self,
                "Laser enable failed",
                str(exc),
            )

    def turn_laser_off(self) -> None:
        """Disable diode output and confirm controller readback."""
        if self.laser is None:
            QMessageBox.warning(
                self,
                "No laser",
                "Connect the laser first.",
            )
            return

        self.set_status(
            "Turning laser off..."
        )

        QApplication.processEvents()

        try:
            self.laser.disable()

            diode_on = (
                self.laser.get_diode_output()
            )
            current_readback = (
                self.laser.get_current()
            )

            self.laser_current.setValue(
                current_readback
            )

            self.set_laser_indicator(
                diode_on
            )

            output_text = (
                "ON" if diode_on else "OFF"
            )

            self.set_status(
                f"Laser output confirmed {output_text}; "
                f"current setpoint "
                f"{current_readback:.3f} A."
            )

        except Exception as exc:
            self.set_status(
                f"Laser shutdown failed: {exc}"
            )

            QMessageBox.critical(
                self,
                "Laser shutdown failed",
                str(exc),
            )

    def set_laser_current(self) -> None:
        """Set current and display the actual controller readback."""
        if self.laser is None:
            QMessageBox.warning(
                self,
                "No laser",
                "Connect the laser first.",
            )
            return

        requested = float(
            self.laser_current.value()
        )

        self.set_status(
            f"Setting laser current to "
            f"{requested:.3f} A..."
        )

        try:
            self.laser.set_current(
                requested
            )

            readback = (
                self.laser.get_current()
            )

            self.laser_current.setValue(
                readback
            )

            self.set_status(
                f"Requested {requested:.3f} A; "
                f"controller readback "
                f"{readback:.3f} A."
            )

        except Exception as exc:
            self.set_status(
                f"Set current failed: {exc}"
            )

            QMessageBox.critical(
                self,
                "Set current failed",
                str(exc),
            )

    # ------------------------------------------------------------------
    # Application lifecycle
    # ------------------------------------------------------------------
    def closeEvent(
        self,
        event: Any,
    ) -> None:
        """Release connected hardware when the window closes."""
        try:
            if self.laser is not None:
                try:
                    self.laser.disable(
                        disable_tec=True
                    )
                finally:
                    self.laser.close()
                    self.laser = None

        except Exception:
            # Window shutdown must still continue if hardware disappears.
            pass

        try:
            if self.spec is not None:
                asyncio.run(
                    self.spec.disconnect()
                )
                self.spec = None

        except Exception:
            pass

        super().closeEvent(event)


def main() -> None:
    """Start the Qt application."""
    import sys

    app = QApplication(sys.argv)

    window = HoribaRangeWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()