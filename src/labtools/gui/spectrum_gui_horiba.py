"""PyQt6 GUI for HORIBA range spectra and optional ITC4000 control.

Each HORIBA operation owns its full asynchronous lifecycle: connect, configure,
acquire, and disconnect all run inside one worker coroutine. This is required
because the HORIBA SDK WebSocket belongs to the asyncio event loop that opened
it. A reusable pre-taken range dark can be captured or loaded for mapping.
"""

from __future__ import annotations

import csv
import traceback
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from labtools.acquisition.range_spectrum import (
    DarkSpectrum,
    capture_range_dark,
    get_range_spectrum,
)
from labtools.devices.horiba_spectrometer import HoribaSpectrometer
from labtools.devices.itc4000 import ITC4000
from labtools.gui.async_runner import AsyncTaskRunner

MAX_LASER_CURRENT_A = 0.100
DEFAULT_LASER_CURRENT_A = 0.080
LASER_THRESHOLD_CURRENT_A = 0.049
DEFAULT_STITCH_OVERLAP_PIXELS = 20


async def _disconnect_safely(spec: HoribaSpectrometer) -> None:
    """Disconnect a HORIBA wrapper without hiding an earlier exception."""
    try:
        await spec.disconnect()
    except Exception as exc:  # noqa: BLE001
        logger.warning("HORIBA disconnect failed: {}", exc)


class HoribaRangeWindow(QMainWindow):
    """Main window for stitched spectra, reusable darks, and laser control."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HORIBA Spectrum Acquisition")
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)

        self.laser: ITC4000 | None = None
        self.pre_taken_dark: DarkSpectrum | None = None
        self._async_tasks: list[tuple[QThread, AsyncTaskRunner]] = []
        self._spectrometer_busy = False

        self._apply_application_style()

        central = QWidget(self)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title_column = QVBoxLayout()
        title = QLabel("HORIBA Spectrum Acquisition")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Configure the detector, acquire stitched spectra, and manage dark corrections"
        )
        subtitle.setObjectName("pageSubtitle")
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        header.addLayout(title_column)
        header.addStretch(1)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        outer.addWidget(splitter, 1)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setFrameShape(QFrame.Shape.NoFrame)
        controls_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        controls_scroll.setMinimumWidth(510)
        controls_scroll.setMaximumWidth(575)

        controls = QWidget()
        controls.setMinimumWidth(490)
        controls.setObjectName("controlsPanel")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(8, 4, 8, 8)
        controls_layout.setSpacing(12)
        self._build_spectrometer_controls(controls_layout)
        self._build_laser_controls(controls_layout)
        controls_layout.addStretch(1)
        controls_scroll.setWidget(controls)
        splitter.addWidget(controls_scroll)

        plot_panel = QFrame()
        plot_panel.setObjectName("plotPanel")
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(14, 12, 14, 12)
        plot_layout.setSpacing(8)

        plot_header = QHBoxLayout()
        plot_title = QLabel("Spectrum")
        plot_title.setObjectName("sectionTitle")
        self.plot_meta = QLabel("No spectrum acquired")
        self.plot_meta.setObjectName("plotMeta")
        plot_header.addWidget(plot_title)
        plot_header.addStretch(1)
        plot_header.addWidget(self.plot_meta)
        plot_layout.addLayout(plot_header)

        self.figure = Figure(figsize=(10, 7), dpi=100)
        self.figure.set_facecolor("#ffffff")
        self.ax = self.figure.add_subplot(111)
        self._style_empty_axes()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.canvas.setMinimumHeight(430)
        self.toolbar = NavigationToolbar(self.canvas, self)
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas, 1)
        splitter.addWidget(plot_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([535, 905])

        self.status = QLabel("Ready")
        self.status.setObjectName("statusText")
        self.status.setWordWrap(True)
        self.statusBar().addWidget(self.status, 1)

        self._connect_signals()
        self._update_frame_controls()
        self._update_background_controls()
        self._toggle_laser_controls(False)
        self._update_spectrometer_buttons()

    def _apply_application_style(self) -> None:
        """Apply a restrained laboratory-instrument visual style."""
        self.setStyleSheet(
            """
            QMainWindow { background: #f3f5f7; }
            QWidget { color: #17212b; font-size: 13px; }
            QLabel#pageTitle { font-size: 25px; font-weight: 700; color: #102a43; }
            QLabel#pageSubtitle { color: #627d98; font-size: 13px; }
            QLabel#sectionTitle { font-size: 17px; font-weight: 700; color: #102a43; }
            QLabel#plotMeta { color: #627d98; }
            QLabel#hintText { color: #627d98; font-size: 12px; }
            QLabel#statusText { color: #334e68; padding: 4px 8px; }
            QFrame#plotPanel, QGroupBox {
                background: #ffffff;
                border: 1px solid #d9e2ec;
                border-radius: 8px;
            }
            QGroupBox {
                margin-top: 13px;
                padding: 14px 10px 10px 10px;
                font-weight: 650;
                color: #243b53;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                min-height: 31px;
                padding: 2px 7px;
                background: #ffffff;
                border: 1px solid #bcccdc;
                border-radius: 5px;
                selection-background-color: #2680c2;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #2680c2;
            }
            QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
            QDoubleSpinBox:disabled { background: #f0f4f8; color: #829ab1; }
            QPushButton {
                min-height: 32px;
                padding: 4px 11px;
                background: #ffffff;
                border: 1px solid #9fb3c8;
                border-radius: 5px;
                color: #243b53;
            }
            QPushButton:hover { background: #f0f4f8; border-color: #627d98; }
            QPushButton:pressed { background: #d9e2ec; }
            QPushButton:disabled { background: #f0f4f8; color: #9fb3c8; border-color: #d9e2ec; }
            QPushButton#primaryButton {
                min-height: 39px;
                background: #0b6fa4;
                border: 1px solid #0b6fa4;
                color: white;
                font-weight: 700;
            }
            QPushButton#primaryButton:hover { background: #095d8a; }
            QPushButton#dangerButton { color: #b42318; border-color: #f0b4ae; }
            QCheckBox { spacing: 7px; }
            QScrollArea { background: transparent; }
            QSplitter::handle { background: transparent; }
            QStatusBar { background: #ffffff; border-top: 1px solid #d9e2ec; }
            """
        )

    def _style_empty_axes(self) -> None:
        """Prepare a clean, readable spectrum canvas."""
        self.ax.clear()
        self.ax.set_xlabel("Wavelength (nm)", fontsize=11)
        self.ax.set_ylabel("Intensity (counts)", fontsize=11)
        self.ax.set_title("Ready for acquisition", fontsize=13, pad=12)
        self.ax.grid(True, color="#d9e2ec", linewidth=0.8, alpha=0.8)
        self.ax.set_facecolor("#fbfcfd")
        self.figure.tight_layout()

    # ------------------------------------------------------------------
    # Build interface
    # ------------------------------------------------------------------
    def _build_spectrometer_controls(self, root: QVBoxLayout) -> None:
        acquisition = QGroupBox("1  Acquisition setup")
        form = QFormLayout(acquisition)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setVerticalSpacing(9)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["syncerity", "symphony"])
        self.preset_combo.setToolTip(
            "Select the detector preset. "
            "The grating turret position is read from the instrument; "
            "the GUI does not force a grating movement."
        )
        form.addRow("Detector preset", self.preset_combo)

        range_widget = QWidget()
        range_layout = QGridLayout(range_widget)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setHorizontalSpacing(8)
        self.start_wl = QDoubleSpinBox()
        self.start_wl.setRange(0.0, 2000.0)
        self.start_wl.setDecimals(2)
        self.start_wl.setValue(600.0)
        self.start_wl.setSuffix(" nm")
        self.end_wl = QDoubleSpinBox()
        self.end_wl.setRange(0.0, 2000.0)
        self.end_wl.setDecimals(2)
        self.end_wl.setValue(900.0)
        self.end_wl.setSuffix(" nm")
        range_layout.addWidget(QLabel("Start"), 0, 0)
        range_layout.addWidget(QLabel("End"), 0, 1)
        range_layout.addWidget(self.start_wl, 1, 0)
        range_layout.addWidget(self.end_wl, 1, 1)
        form.addRow("Spectral range", range_widget)

        self.exposure_box = QDoubleSpinBox()
        self.exposure_box.setRange(0.001, 1000.0)
        self.exposure_box.setDecimals(3)
        self.exposure_box.setSingleStep(0.1)
        self.exposure_box.setValue(0.5)
        self.exposure_box.setSuffix(" s")
        form.addRow("Exposure", self.exposure_box)

        repeat_widget = QWidget()
        repeat_layout = QGridLayout(repeat_widget)
        repeat_layout.setContentsMargins(0, 0, 0, 0)
        repeat_layout.setHorizontalSpacing(8)
        self.frames_box = QSpinBox()
        self.frames_box.setRange(1, 100)
        self.frames_box.setValue(1)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["single", "mean", "median", "sigma_clip"])
        repeat_layout.addWidget(QLabel("Frames"), 0, 0)
        repeat_layout.addWidget(QLabel("Combine"), 0, 1)
        repeat_layout.addWidget(self.frames_box, 1, 0)
        repeat_layout.addWidget(self.mode_combo, 1, 1)
        form.addRow("Repeats", repeat_widget)

        self.overlap_box = QSpinBox()
        self.overlap_box.setRange(0, 1000)
        self.overlap_box.setValue(DEFAULT_STITCH_OVERLAP_PIXELS)
        self.overlap_box.setSuffix(" pixels")
        form.addRow("Stitch overlap", self.overlap_box)

        self.slit_width_box = QDoubleSpinBox()
        self.slit_width_box.setRange(
            0.001,
            10.000,
        )
        self.slit_width_box.setDecimals(3)
        self.slit_width_box.setSingleStep(0.050)
        self.slit_width_box.setValue(0.500)
        self.slit_width_box.setSuffix(" mm")
        self.slit_width_box.setToolTip(
            "Set the width of monochromator slit A. "
            "Use values supported by the spectrometer "
            "configuration and firmware."
        )

        form.addRow(
            "Slit A width",
            self.slit_width_box,
        )

        hint = QLabel(
            "Required: detector, wavelength range, exposure, and frame combination."
        )
        hint.setObjectName("hintText")
        hint.setWordWrap(True)
        form.addRow("", hint)
        root.addWidget(acquisition)

        dark_group = QGroupBox("2  Dark correction")
        dark_form = QFormLayout(dark_group)
        dark_form.setVerticalSpacing(9)
        self.use_background = QCheckBox("Enable dark subtraction")
        dark_form.addRow("", self.use_background)

        self.background_mode = QComboBox()
        self.background_mode.addItems(
            [
                "Capture during acquisition",
                "Use pre-taken stitched dark",
            ]
        )
        dark_form.addRow("Source", self.background_mode)

        self.background_timing = QComboBox()
        self.background_timing.addItems(
            [
                "One dark per centre wavelength",
                "One dark per repeated frame",
            ]
        )
        dark_form.addRow("Timing", self.background_timing)

        self.capture_dark_button = QPushButton("Capture reusable dark")
        self.load_dark_button = QPushButton("Load dark CSV")
        self.clear_dark_button = QPushButton("Clear")
        self.clear_dark_button.setObjectName("dangerButton")
        dark_buttons = QGridLayout()
        dark_buttons.addWidget(self.capture_dark_button, 0, 0, 1, 2)
        dark_buttons.addWidget(self.load_dark_button, 1, 0)
        dark_buttons.addWidget(self.clear_dark_button, 1, 1)
        dark_form.addRow("Pre-taken dark", dark_buttons)

        self.background_status = QLabel("Dark subtraction disabled")
        self.background_status.setObjectName("hintText")
        self.background_status.setWordWrap(True)
        dark_form.addRow("", self.background_status)
        root.addWidget(dark_group)

        output_group = QGroupBox("3  Output")
        output_layout = QVBoxLayout(output_group)
        save_row = QHBoxLayout()
        self.save_csv = QCheckBox("Save CSV")
        self.save_png = QCheckBox("Save PNG")
        save_row.addWidget(self.save_csv)
        save_row.addWidget(self.save_png)
        save_row.addStretch(1)
        output_layout.addLayout(save_row)
        root.addWidget(output_group)

        self.connect_button = QPushButton("Test connection")
        self.acquire_button = QPushButton("Acquire spectrum")
        self.acquire_button.setObjectName("primaryButton")
        root.addWidget(self.connect_button)
        root.addWidget(self.acquire_button)

    def _build_laser_controls(self, root: QVBoxLayout) -> None:
        self.laser_group = QGroupBox("Laser control  (optional)")
        self.laser_group.setCheckable(True)
        self.laser_group.setChecked(False)
        form = QFormLayout(self.laser_group)
        form.setVerticalSpacing(9)

        self.laser_address = QLineEdit(ITC4000.DEFAULT_ADDRESS)
        form.addRow("VISA address", self.laser_address)

        self.laser_current = QDoubleSpinBox()
        self.laser_current.setRange(0.0, MAX_LASER_CURRENT_A)
        self.laser_current.setDecimals(3)
        self.laser_current.setSingleStep(0.001)
        self.laser_current.setValue(DEFAULT_LASER_CURRENT_A)
        self.laser_current.setSuffix(" A")
        form.addRow("Drive current", self.laser_current)

        self.laser_light = QLabel("Laser output: OFF")
        self.laser_light.setMinimumHeight(34)
        self.laser_light.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_laser_indicator(False)
        form.addRow("Status", self.laser_light)

        self.laser_connect = QPushButton("Connect")
        self.laser_on = QPushButton("Output ON")
        self.laser_off = QPushButton("Output OFF")
        self.laser_set = QPushButton("Apply current")
        row = QGridLayout()
        row.addWidget(self.laser_connect, 0, 0)
        row.addWidget(self.laser_set, 0, 1)
        row.addWidget(self.laser_on, 1, 0)
        row.addWidget(self.laser_off, 1, 1)
        form.addRow(row)
        root.addWidget(self.laser_group)

    def _connect_signals(self) -> None:
        self.connect_button.clicked.connect(self.test_spectrometer_connection)
        self.acquire_button.clicked.connect(self.acquire_spectrum)
        self.capture_dark_button.clicked.connect(self.capture_reusable_dark)
        self.load_dark_button.clicked.connect(self.load_pre_taken_dark)
        self.clear_dark_button.clicked.connect(self.clear_pre_taken_dark)
        self.mode_combo.currentTextChanged.connect(self._update_frame_controls)
        self.use_background.toggled.connect(self._update_background_controls)
        self.background_mode.currentTextChanged.connect(
            self._update_background_controls
        )

        self.laser_group.toggled.connect(self._toggle_laser_controls)
        self.laser_connect.clicked.connect(self.connect_laser)
        self.laser_on.clicked.connect(self.turn_laser_on)
        self.laser_off.clicked.connect(self.turn_laser_off)
        self.laser_set.clicked.connect(self.set_laser_current)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def set_status(self, message: str) -> None:
        self.status.setText(message)

    @staticmethod
    def _exception_summary(error: str) -> str:
        lines = [line.strip() for line in error.splitlines() if line.strip()]
        return lines[-1] if lines else error

    def _show_error(self, title: str, summary: str, details: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(summary)
        box.setDetailedText(details)
        box.exec()

    def _normalised_range(self) -> tuple[float, float]:
        start = float(self.start_wl.value())
        end = float(self.end_wl.value())
        if start == end:
            raise ValueError("Start and end wavelengths must be different.")
        if end < start:
            start, end = end, start
            self.start_wl.setValue(start)
            self.end_wl.setValue(end)
        return start, end

    def _set_spectrometer_busy(self, busy: bool) -> None:
        self._spectrometer_busy = busy
        self._update_spectrometer_buttons()

    def _update_spectrometer_buttons(self) -> None:
        idle = not self._spectrometer_busy
        self.connect_button.setEnabled(idle)
        self.acquire_button.setEnabled(idle)
        self.capture_dark_button.setEnabled(idle)
        self.preset_combo.setEnabled(idle)
        self.exposure_box.setEnabled(idle)
        self.overlap_box.setEnabled(idle)
        self.slit_width_box.setEnabled(idle)

    def _update_frame_controls(self) -> None:
        mode = self.mode_combo.currentText()
        minimum = 1 if mode == "single" else 3 if mode == "sigma_clip" else 2
        self.frames_box.setMinimum(minimum)
        self.frames_box.setEnabled(mode != "single")
        if mode == "single":
            self.frames_box.setValue(1)
        elif self.frames_box.value() < minimum:
            self.frames_box.setValue(minimum)

    def _update_background_controls(self) -> None:
        enabled = self.use_background.isChecked()
        use_pre_taken = (
            self.background_mode.currentText() == "Use pre-taken stitched dark"
        )
        self.background_mode.setEnabled(enabled)
        self.background_timing.setEnabled(enabled and not use_pre_taken)
        self.load_dark_button.setEnabled(enabled and use_pre_taken)
        self.clear_dark_button.setEnabled(self.pre_taken_dark is not None)

        if not enabled:
            text = "Dark subtraction disabled"
        elif use_pre_taken and self.pre_taken_dark is None:
            text = "Load or capture a reusable stitched dark before acquisition."
        elif use_pre_taken:
            text = (
                f"Reusable dark loaded: {self.pre_taken_dark.wavelength_nm.size} points"
            )
        elif self.background_timing.currentIndex() == 0:
            text = "One dark will be acquired and reused at each centre wavelength."
        else:
            text = "Every repeated signal frame will be paired with a new dark."
        self.background_status.setText(text)

    def _selected_dark_mode(self) -> str:
        if not self.use_background.isChecked():
            return "none"
        if self.background_mode.currentText() == "Use pre-taken stitched dark":
            return "pre_taken"
        return (
            "per_center" if self.background_timing.currentIndex() == 0 else "per_frame"
        )

    # ------------------------------------------------------------------
    # Async helper
    # ------------------------------------------------------------------
    def _run_async(
        self,
        coroutine_factory: Callable[[], Coroutine[Any, Any, Any]],
        on_done: Callable[[Any], None],
        on_error: Callable[[str], None],
    ) -> None:
        thread = QThread(self)
        runner = AsyncTaskRunner(coroutine_factory)
        runner.moveToThread(thread)
        task = (thread, runner)
        self._async_tasks.append(task)

        thread.started.connect(runner.run)
        runner.finished.connect(on_done)
        runner.failed.connect(on_error)
        runner.finished.connect(thread.quit)
        runner.failed.connect(thread.quit)
        runner.finished.connect(runner.deleteLater)
        runner.failed.connect(runner.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def cleanup(_: object = None) -> None:
            if task in self._async_tasks:
                self._async_tasks.remove(task)

        runner.finished.connect(cleanup)
        runner.failed.connect(cleanup)
        thread.start()

    # ------------------------------------------------------------------
    # HORIBA operations: each owns connect/configure/work/disconnect
    # ------------------------------------------------------------------
    def test_spectrometer_connection(self) -> None:
        """Connect, configure, then disconnect within one event loop."""
        if self._spectrometer_busy:
            return
        self._set_spectrometer_busy(True)
        self.set_status("Testing HORIBA connection and configuration...")
        preset = self.preset_combo.currentText()
        exposure = float(self.exposure_box.value())
        slit_name = "A"
        slit_width_mm = float(self.slit_width_box.value())

        async def test() -> str:
            spec = HoribaSpectrometer(preset=preset)
            try:
                await spec.connect()
                await spec.configure(
                    gain=2,
                    speed=0,
                    exposure_time=exposure,
                    roi={},
                )

                reported_slit_width_mm = await spec.set_slit_width(
                    slit_name,
                    slit_width_mm,
                )

                return (
                    f"{preset}; slit {slit_name} "
                    f"reported "
                    f"{reported_slit_width_mm:.3f} mm"
                )
            finally:
                await _disconnect_safely(spec)

        self._run_async(
            lambda: test(),
            self._handle_connection_test_done,
            self._handle_connection_error,
        )

    def _handle_connection_test_done(self, preset: str) -> None:
        self._set_spectrometer_busy(False)
        self.set_status(
            f"HORIBA preset '{preset}' connected and configured successfully; "
            "the test connection was closed cleanly."
        )

    def _handle_connection_error(self, error: str) -> None:
        self._set_spectrometer_busy(False)
        summary = self._exception_summary(error)
        self.set_status(f"Spectrometer connection failed: {summary}")
        self._show_error("Spectrometer connection failed", summary, error)

    def acquire_spectrum(self) -> None:
        """Connect, configure, acquire one range, and disconnect."""
        if self._spectrometer_busy:
            return
        try:
            start, end = self._normalised_range()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid range", str(exc))
            return

        dark_mode = self._selected_dark_mode()
        if dark_mode == "pre_taken" and self.pre_taken_dark is None:
            QMessageBox.warning(
                self,
                "No pre-taken dark",
                "Load or capture a reusable stitched dark before acquisition.",
            )
            return

        preset = self.preset_combo.currentText()
        exposure = float(self.exposure_box.value())
        n_frames = int(self.frames_box.value())
        combine_mode = self.mode_combo.currentText()
        overlap = int(self.overlap_box.value())
        slit_name = "A"
        slit_width_mm = float(self.slit_width_box.value())
        pre_taken_dark = self.pre_taken_dark if dark_mode == "pre_taken" else None

        self._set_spectrometer_busy(True)
        self.set_status(
            f"Connecting and acquiring {start:.2f}-{end:.2f} nm; "
            f"dark mode: {dark_mode}..."
        )

        async def acquire() -> tuple[np.ndarray, np.ndarray]:
            spec = HoribaSpectrometer(preset=preset)
            try:
                await spec.connect()
                await spec.configure(
                    gain=2,
                    speed=0,
                    exposure_time=exposure,
                    roi={},
                )

                reported_slit_width_mm = await spec.set_slit_width(
                    slit_name,
                    slit_width_mm,
                )

                logger.info(
                    "Acquiring with slit {} at {:.3f} mm",
                    slit_name,
                    reported_slit_width_mm,
                )

                return await get_range_spectrum(
                    spec,
                    start,
                    end,
                    stitch_pixel_overlap=overlap,
                    n_frames=n_frames,
                    mode=combine_mode,
                    dark_mode=dark_mode,
                    pre_taken_dark=pre_taken_dark,
                )
            finally:
                await _disconnect_safely(spec)

        self._run_async(
            lambda: acquire(),
            self._handle_acquire_done,
            self._handle_acquire_error,
        )

    def _handle_acquire_done(self, result: tuple[Any, Any]) -> None:
        self._set_spectrometer_busy(False)
        x_data, y_data = result

        self.ax.clear()
        self.ax.plot(
            x_data,
            y_data,
            color="#0b6fa4",
            linewidth=1.35,
            label="Measured spectrum",
        )
        self.ax.set_xlabel("Wavelength (nm)", fontsize=11)
        self.ax.set_ylabel("Intensity (counts)", fontsize=11)
        self.ax.set_title("HORIBA range spectrum", fontsize=14, pad=12)
        self.ax.grid(True, color="#d9e2ec", linewidth=0.8, alpha=0.85)
        self.ax.set_facecolor("#fbfcfd")
        self.ax.margins(x=0.01, y=0.08)
        self.figure.tight_layout()
        self.canvas.draw_idle()
        wavelength_min = float(np.min(x_data))
        wavelength_max = float(np.max(x_data))
        self.plot_meta.setText(
            f"{wavelength_min:.2f}-{wavelength_max:.2f} nm  |  {len(x_data)} points"
        )

        try:
            saved = self._maybe_save_result(x_data, y_data)
        except Exception as exc:  # noqa: BLE001
            self.set_status(f"Acquisition succeeded, but saving failed: {exc}")
            self._show_error("Save failed", str(exc), traceback.format_exc())
            return

        suffix = f" Saved to {saved}." if saved else ""
        wavelength_min = float(np.min(x_data))
        wavelength_max = float(np.max(x_data))
        self.set_status(
            f"Spectrum acquired successfully: {wavelength_min:.2f}-"
            f"{wavelength_max:.2f} nm, {len(x_data)} points.{suffix}"
        )

    def _handle_acquire_error(self, error: str) -> None:
        self._set_spectrometer_busy(False)
        summary = self._exception_summary(error)
        self.set_status(f"Acquisition failed: {summary}")
        self._show_error("Acquisition failed", summary, error)

    def capture_reusable_dark(self) -> None:
        """Connect, capture a stitched range dark, and disconnect."""
        if self._spectrometer_busy:
            return
        try:
            start, end = self._normalised_range()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid range", str(exc))
            return

        preset = self.preset_combo.currentText()
        exposure = float(self.exposure_box.value())
        n_frames = int(self.frames_box.value())
        mode = self.mode_combo.currentText()
        overlap = int(self.overlap_box.value())
        slit_name = "A"
        slit_width_mm = float(self.slit_width_box.value())

        self._set_spectrometer_busy(True)
        self.set_status(
            f"Connecting and capturing reusable dark over {start:.2f}-{end:.2f} nm..."
        )

        async def capture() -> DarkSpectrum:
            spec = HoribaSpectrometer(preset=preset)
            try:
                await spec.connect()
                await spec.configure(
                    gain=2,
                    speed=0,
                    exposure_time=exposure,
                    roi={},
                )

                reported_slit_width_mm = await spec.set_slit_width(
                    slit_name,
                    slit_width_mm,
                )

                logger.info(
                    "Capturing reusable dark with slit {} at {:.3f} mm",
                    slit_name,
                    reported_slit_width_mm,
                )

                return await capture_range_dark(
                    spec,
                    start,
                    end,
                    stitch_pixel_overlap=overlap,
                    n_frames=n_frames,
                    mode=mode,
                )
            finally:
                await _disconnect_safely(spec)

        self._run_async(
            lambda: capture(),
            self._handle_dark_capture_done,
            self._handle_dark_capture_error,
        )

    def _handle_dark_capture_done(self, dark: DarkSpectrum) -> None:
        self._set_spectrometer_busy(False)
        self.pre_taken_dark = dark
        self.use_background.setChecked(True)
        self.background_mode.setCurrentText("Use pre-taken stitched dark")
        self._update_background_controls()

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save reusable range dark",
            str(Path.cwd() / "range_dark.csv"),
            "CSV files (*.csv)",
        )
        if path:
            try:
                dark.save_csv(path)
                self.set_status(f"Reusable dark captured and saved to {path}.")
            except Exception as exc:  # noqa: BLE001
                self.set_status(f"Dark captured, but saving failed: {exc}")
                self._show_error("Save dark failed", str(exc), traceback.format_exc())
        else:
            self.set_status("Reusable dark captured and retained in memory.")

    def _handle_dark_capture_error(self, error: str) -> None:
        self._set_spectrometer_busy(False)
        summary = self._exception_summary(error)
        self.set_status(f"Reusable dark capture failed: {summary}")
        self._show_error("Dark capture failed", summary, error)

    def load_pre_taken_dark(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load reusable range dark",
            str(Path.cwd()),
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            self.pre_taken_dark = DarkSpectrum.load_csv(path)
        except Exception as exc:  # noqa: BLE001
            self._show_error("Load dark failed", str(exc), traceback.format_exc())
            return

        self.use_background.setChecked(True)
        self.background_mode.setCurrentText("Use pre-taken stitched dark")
        self._update_background_controls()
        self.set_status(f"Loaded reusable range dark from {path}.")

    def clear_pre_taken_dark(self) -> None:
        self.pre_taken_dark = None
        self._update_background_controls()
        self.set_status("Cleared the pre-taken range dark.")

    def _maybe_save_result(self, x_data: Any, y_data: Any) -> Path | None:
        if not (self.save_csv.isChecked() or self.save_png.isChecked()):
            return None

        output_dir = Path.cwd() / "spectra"
        output_dir.mkdir(exist_ok=True)
        start, end = self._normalised_range()
        stem = f"horiba_{start:.0f}_{end:.0f}nm"

        if self.save_csv.isChecked():
            with (output_dir / f"{stem}.csv").open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["wavelength_nm", "intensity"])
                writer.writerows(
                    (float(wavelength), float(intensity))
                    for wavelength, intensity in zip(x_data, y_data, strict=True)
                )
        if self.save_png.isChecked():
            self.figure.savefig(output_dir / f"{stem}.png", dpi=200)
        return output_dir

    # ------------------------------------------------------------------
    # Laser control
    # ------------------------------------------------------------------
    def set_laser_indicator(self, on: bool) -> None:
        if on:
            self.laser_light.setText("Laser output: ON")
            color, border = "#1f5a2a", "#5fd17a"
        else:
            self.laser_light.setText("Laser output: OFF")
            color, border = "#3a3a3a", "#666"
        self.laser_light.setStyleSheet(
            "QLabel { "
            f"background-color: {color}; color: white; border: 1px solid {border}; "
            "border-radius: 8px; padding: 6px; }"
        )

    def _toggle_laser_controls(self, enabled: bool) -> None:
        connected = self.laser is not None
        self.laser_address.setEnabled(enabled and not connected)
        self.laser_current.setEnabled(enabled)
        self.laser_connect.setEnabled(enabled)
        self.laser_on.setEnabled(enabled and connected)
        self.laser_off.setEnabled(enabled and connected)
        self.laser_set.setEnabled(enabled and connected)

    def connect_laser(self) -> None:
        address = self.laser_address.text().strip() or ITC4000.DEFAULT_ADDRESS
        self.laser_connect.setEnabled(False)
        self.set_status(f"Connecting to laser at {address}...")
        try:
            if self.laser is not None:
                self.laser.close()

            laser = ITC4000(
                address,
                threshold_current=LASER_THRESHOLD_CURRENT_A,
                max_current=MAX_LASER_CURRENT_A,
            )
            try:
                identity = laser.identify()
                current = laser.get_current()
                diode_on = laser.get_diode_output()
                tec_on = laser.get_tec_output()
            except Exception:
                laser.close()
                raise

            self.laser = laser
            self.laser_current.setValue(current)
            self.set_laser_indicator(diode_on)
            self._toggle_laser_controls(True)
            self.set_status(
                f"Connected: {identity} | Current: {current:.3f} A | "
                f"LD: {'ON' if diode_on else 'OFF'} | TEC: {'ON' if tec_on else 'OFF'}"
            )
        except Exception as exc:  # noqa: BLE001
            self.laser = None
            self.set_laser_indicator(False)
            self._toggle_laser_controls(True)
            self.set_status(f"Laser connection failed: {exc}")
            self._show_error(
                "Laser connection failed", str(exc), traceback.format_exc()
            )
        finally:
            self.laser_connect.setEnabled(True)

    def turn_laser_on(self) -> None:
        if self.laser is None:
            QMessageBox.warning(self, "No laser", "Connect the laser first.")
            return
        current = float(self.laser_current.value())
        self.set_status(f"Turning laser on at {current:.3f} A...")
        QApplication.processEvents()
        try:
            self.laser.enable(current=current)
            on = self.laser.get_diode_output()
            readback = self.laser.get_current()
            self.set_laser_indicator(on)
            self.set_status(
                f"Laser output {'ON' if on else 'OFF'}; current {readback:.3f} A."
            )
        except Exception as exc:  # noqa: BLE001
            self.set_laser_indicator(False)
            self._show_error("Laser enable failed", str(exc), traceback.format_exc())

    def turn_laser_off(self) -> None:
        if self.laser is None:
            QMessageBox.warning(self, "No laser", "Connect the laser first.")
            return
        try:
            self.laser.disable()
            on = self.laser.get_diode_output()
            readback = self.laser.get_current()
            self.laser_current.setValue(readback)
            self.set_laser_indicator(on)
            self.set_status(
                f"Laser output {'ON' if on else 'OFF'}; current {readback:.3f} A."
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error("Laser shutdown failed", str(exc), traceback.format_exc())

    def set_laser_current(self) -> None:
        if self.laser is None:
            QMessageBox.warning(self, "No laser", "Connect the laser first.")
            return
        requested = float(self.laser_current.value())
        try:
            self.laser.set_current(requested)
            readback = self.laser.get_current()
            self.laser_current.setValue(readback)
            self.set_status(
                f"Requested {requested:.3f} A; controller readback {readback:.3f} A."
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error("Set current failed", str(exc), traceback.format_exc())

    def closeEvent(self, event: Any) -> None:
        """Close the persistent laser session; HORIBA sessions are task-local."""
        if self._spectrometer_busy:
            QMessageBox.warning(
                self,
                "Operation in progress",
                "Wait for the spectrometer operation to finish before closing.",
            )
            event.ignore()
            return

        if self.laser is not None:
            try:
                self.laser.disable(disable_tec=True)
            except Exception:  # noqa: BLE001
                logger.warning("Laser shutdown failed while closing the GUI")
            finally:
                self.laser.close()
                self.laser = None
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
