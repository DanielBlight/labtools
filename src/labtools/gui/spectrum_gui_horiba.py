"""PyQt6 GUI for HORIBA range spectra and optional ITC4000 control.

Each HORIBA operation owns its full asynchronous lifecycle: connect, configure,
acquire, and disconnect all run inside one worker coroutine. This is required
because the HORIBA SDK WebSocket belongs to the asyncio event loop that opened
it. A reusable pre-taken range dark can be captured or loaded for mapping.
"""

from __future__ import annotations

import csv
import os
import traceback
from pathlib import Path
from threading import Event
from typing import Any

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

from labtools.acquisition.spectrum_service import (
    DarkRecord,
    SpectrumResult,
    SpectrumService,
)
from labtools.config.spectrum import SpectrumSettings
from labtools.gui.async_runner import AsyncTaskRunner
from labtools.io.spectrum_records import (
    load_dark_record,
    save_dark_record,
    save_spectrum_result,
)
from labtools.runtime.lazy_devices import LazyITC4000 as ITC4000
from labtools.runtime.spectrum_backend import create_spectrum_service


def _real_preset_options() -> dict[str, dict]:
    """Load authoritative wrapper options only for the real standalone GUI."""
    from labtools.devices.horiba_spectrometer import HoribaSpectrometer

    return {
        name: HoribaSpectrometer.preset_options(name)
        for name in ("syncerity", "symphony")
    }


MAX_LASER_CURRENT_A = 0.100
DEFAULT_LASER_CURRENT_A = 0.080
LASER_THRESHOLD_CURRENT_A = 0.049
DEFAULT_STITCH_OVERLAP_PIXELS = 20
DEFAULT_OUTPUT_DIRECTORY = Path.cwd() / "spectra"


class HoribaRangeWindow(QMainWindow):
    """Main window for stitched spectra, reusable darks, and laser control."""

    def __init__(
        self,
        *,
        service: SpectrumService | None = None,
        configuration_id: str | None = None,
        backend: str = "real",
        preset_options: dict[str, dict] | None = None,
    ) -> None:
        super().__init__()
        if backend not in {"real", "simulation"}:
            raise ValueError("Explicit real or simulation backend required")
        self._backend = backend
        self._configuration_id = configuration_id
        if (
            not isinstance(self._configuration_id, str)
            or not self._configuration_id.strip()
        ):
            raise ValueError(
                "A maintainer-supplied spectrum configuration_id is required"
            )
        self._preset_options = (
            preset_options if preset_options is not None else _real_preset_options()
        )
        self._service = (
            service if service is not None else create_spectrum_service(backend=backend)
        )
        self._cancel_event = Event()
        self.latest_result: SpectrumResult | None = None
        self._save_options: tuple[bool, bool, Path] | None = None
        self.setWindowTitle("HORIBA Spectrum Acquisition")
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)

        self.laser: ITC4000 | None = None
        self.pre_taken_dark: DarkRecord | None = None
        self._async_tasks: list[tuple[QThread, AsyncTaskRunner]] = []
        self._spectrometer_busy = False
        self._operation_outcome = None

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
            "The selected preset verifies detector identity, grating, exit "
            "mirror and detector settings before acquisition."
        )
        form.addRow("Detector preset", self.preset_combo)

        range_widget = QWidget()
        range_layout = QGridLayout(range_widget)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setHorizontalSpacing(8)
        self.start_wl = QDoubleSpinBox()
        self.start_wl.setRange(0.0, 2200.0)
        self.start_wl.setDecimals(2)
        self.start_wl.setValue(600.0)
        self.start_wl.setSuffix(" nm")
        self.end_wl = QDoubleSpinBox()
        self.end_wl.setRange(0.0, 2200.0)
        self.end_wl.setDecimals(2)
        self.end_wl.setValue(900.0)
        self.end_wl.setSuffix(" nm")
        range_layout.addWidget(QLabel("Start"), 0, 0)
        range_layout.addWidget(QLabel("End"), 0, 1)
        range_layout.addWidget(self.start_wl, 1, 0)
        range_layout.addWidget(self.end_wl, 1, 1)
        form.addRow("Spectral range", range_widget)

        self.exposure_box = QDoubleSpinBox()
        self.exposure_box.setRange(0.065, 1000.0)
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

        hint = QLabel(
            "The selected preset is checked and applied when connecting or acquiring."
        )
        hint.setObjectName("hintText")
        hint.setWordWrap(True)
        form.addRow("", hint)
        root.addWidget(acquisition)

        self.advanced_group = QGroupBox("Advanced detector settings")
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        advanced_layout = QVBoxLayout(self.advanced_group)
        advanced_layout.setContentsMargins(12, 8, 12, 12)

        self.advanced_content = QWidget()
        advanced_form = QFormLayout(self.advanced_content)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        advanced_form.setVerticalSpacing(9)

        self.gain_combo = QComboBox()
        self.speed_combo = QComboBox()
        advanced_form.addRow("Gain", self.gain_combo)
        advanced_form.addRow("Readout speed", self.speed_combo)

        self.overlap_box = QSpinBox()
        self.overlap_box.setRange(0, 1000)
        self.overlap_box.setValue(DEFAULT_STITCH_OVERLAP_PIXELS)
        self.overlap_box.setSuffix(" pixels")
        advanced_form.addRow("Stitch overlap", self.overlap_box)

        self.slit_width_box = QDoubleSpinBox()
        self.slit_width_box.setRange(0.001, 10.000)
        self.slit_width_box.setDecimals(3)
        self.slit_width_box.setSingleStep(0.050)
        self.slit_width_box.setValue(0.500)
        self.slit_width_box.setSuffix(" mm")
        self.slit_width_box.setToolTip("Set and verify monochromator entrance Slit A.")
        advanced_form.addRow("Entrance slit width", self.slit_width_box)

        advanced_layout.addWidget(self.advanced_content)
        self.advanced_content.setVisible(False)
        root.addWidget(self.advanced_group)

        dark_group = QGroupBox("2  Dark correction")
        dark_form = QFormLayout(dark_group)
        dark_form.setVerticalSpacing(9)
        self.use_background = QCheckBox("Enable dark subtraction")
        dark_form.addRow("", self.use_background)
        self.background_mode = QComboBox()
        self.background_mode.addItems(
            ["Capture during acquisition", "Use pre-taken stitched dark"]
        )
        dark_form.addRow("Source", self.background_mode)
        self.background_timing = QComboBox()
        self.background_timing.addItems(
            ["One dark per centre wavelength", "One dark per repeated frame"]
        )
        dark_form.addRow("Timing", self.background_timing)
        self.capture_dark_button = QPushButton("Capture reusable dark")
        self.load_dark_button = QPushButton("Load dark NPZ")
        self.stop_button = QPushButton("Stop after current acquisition")
        self.stop_button.setEnabled(False)
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
        output_form = QFormLayout(output_group)
        output_form.setVerticalSpacing(9)
        save_row = QHBoxLayout()
        self.save_csv = QCheckBox("Save CSV")
        self.save_png = QCheckBox("Save PNG")
        save_row.addWidget(self.save_csv)
        save_row.addWidget(self.save_png)
        save_row.addStretch(1)
        output_form.addRow("Formats", save_row)

        output_path_widget = QWidget()
        output_path_layout = QHBoxLayout(output_path_widget)
        output_path_layout.setContentsMargins(0, 0, 0, 0)
        output_path_layout.setSpacing(6)
        self.output_directory = QLineEdit(str(DEFAULT_OUTPUT_DIRECTORY))
        self.output_directory.setToolTip("Directory used for CSV, PNG and dark files.")
        self.output_browse_button = QPushButton("Browse...")
        output_path_layout.addWidget(self.output_directory, 1)
        output_path_layout.addWidget(self.output_browse_button)
        output_form.addRow("Output folder", output_path_widget)
        root.addWidget(output_group)

        self.connect_button = QPushButton("Test connection")
        self.acquire_button = QPushButton("Acquire spectrum")
        self.acquire_button.setObjectName("primaryButton")
        root.addWidget(self.connect_button)
        root.addWidget(self.acquire_button)

        self._update_preset_controls()

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
        self.stop_button.clicked.connect(self.request_stop)
        self.capture_dark_button.clicked.connect(self.capture_reusable_dark)
        self.load_dark_button.clicked.connect(self.load_pre_taken_dark)
        self.clear_dark_button.clicked.connect(self.clear_pre_taken_dark)
        self.mode_combo.currentTextChanged.connect(self._update_frame_controls)
        self.mode_combo.currentTextChanged.connect(self._update_background_controls)
        self.preset_combo.currentTextChanged.connect(self._update_preset_controls)
        self.advanced_group.toggled.connect(self._update_advanced_controls)
        self.output_browse_button.clicked.connect(self._browse_output_directory)
        self.use_background.toggled.connect(self._update_background_controls)
        self.background_mode.currentTextChanged.connect(
            self._update_background_controls
        )

        for widget in (
            self.preset_combo,
            self.exposure_box,
            self.frames_box,
            self.mode_combo,
            self.gain_combo,
            self.speed_combo,
            self.overlap_box,
            self.slit_width_box,
            self.start_wl,
            self.end_wl,
        ):
            signal = (
                widget.valueChanged
                if hasattr(widget, "valueChanged")
                else widget.currentIndexChanged
            )
            signal.connect(self._update_background_controls)
        self.advanced_group.toggled.connect(self._update_background_controls)
        self.background_timing.currentIndexChanged.connect(
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

    def _update_preset_controls(self) -> None:
        """Populate detector-specific gain and speed descriptions."""
        preset = self.preset_combo.currentText()
        options = self._preset_options[preset]

        self.gain_combo.clear()
        for label, token in options["gains"]:
            self.gain_combo.addItem(label, token)
        gain_index = self.gain_combo.findData(options["default_gain"])
        self.gain_combo.setCurrentIndex(max(0, gain_index))

        self.speed_combo.clear()
        for label, token in options["speeds"]:
            self.speed_combo.addItem(label, token)
        speed_index = self.speed_combo.findData(options["default_speed"])
        self.speed_combo.setCurrentIndex(max(0, speed_index))

        self.exposure_box.setMinimum(options["minimum_exposure_s"])
        if self.exposure_box.value() < options["minimum_exposure_s"]:
            self.exposure_box.setValue(options["minimum_exposure_s"])
        self._update_advanced_controls()

    def _update_advanced_controls(self) -> None:
        """Expand advanced controls only while the group is checked."""
        checked = self.advanced_group.isChecked()
        self.advanced_content.setVisible(checked)

        enabled = checked and not self._spectrometer_busy
        self.gain_combo.setEnabled(enabled)
        self.speed_combo.setEnabled(enabled)
        self.overlap_box.setEnabled(enabled)
        self.slit_width_box.setEnabled(enabled)

    def _selected_detector_settings(self) -> tuple[int, int]:
        """Return preset defaults or explicit advanced overrides."""
        preset = self.preset_combo.currentText()
        options = self._preset_options[preset]
        if not self.advanced_group.isChecked():
            return int(options["default_gain"]), int(options["default_speed"])
        return int(self.gain_combo.currentData()), int(self.speed_combo.currentData())

    def _selected_output_directory(self) -> Path:
        text = self.output_directory.text().strip()
        output_dir = Path(text).expanduser() if text else DEFAULT_OUTPUT_DIRECTORY
        return output_dir.resolve()

    def _browse_output_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select spectrum output folder",
            str(self._selected_output_directory()),
        )
        if selected:
            self.output_directory.setText(selected)

    def _set_spectrometer_busy(self, busy: bool) -> None:
        self._spectrometer_busy = busy
        self._update_spectrometer_buttons()

    def _update_spectrometer_buttons(self) -> None:
        idle = not self._spectrometer_busy
        self.connect_button.setEnabled(idle)
        self.acquire_button.setEnabled(idle)
        self.capture_dark_button.setEnabled(idle)
        self.stop_button.setEnabled(not idle and not self._cancel_event.is_set())
        self.preset_combo.setEnabled(idle)
        self.exposure_box.setEnabled(idle)
        self.advanced_group.setEnabled(idle)
        self.output_directory.setEnabled(idle)
        self.output_browse_button.setEnabled(idle)
        self.load_dark_button.setEnabled(
            idle
            and self.use_background.isChecked()
            and self.background_mode.currentIndex() == 1
        )
        self.clear_dark_button.setEnabled(idle and self.pre_taken_dark is not None)
        self._update_advanced_controls()

    def _update_frame_controls(self) -> None:
        mode = self.mode_combo.currentText()
        minimum = (
            1 if mode == "single" else 3 if mode in {"median", "sigma_clip"} else 2
        )
        self.frames_box.setMinimum(minimum)
        self.frames_box.setEnabled(mode != "single")
        if mode == "single":
            self.frames_box.setValue(1)
        elif self.frames_box.value() < minimum:
            self.frames_box.setValue(minimum)

    def _snapshot_settings(self) -> SpectrumSettings:
        """Read all acquisition inputs on the UI thread, never inside a worker."""
        start, end = self._normalised_range()
        gain, speed = self._selected_detector_settings()
        settings = SpectrumSettings(
            configuration_id=self._configuration_id,
            preset=self.preset_combo.currentText(),
            exposure_s=float(self.exposure_box.value()),
            gain=gain,
            speed=speed,
            slit_width_mm=float(self.slit_width_box.value()),
            start_nm=start,
            end_nm=end,
            overlap_pixels=int(self.overlap_box.value()),
            n_frames=int(self.frames_box.value()),
            combine_mode=self.mode_combo.currentText(),
            backend=self._backend,
        )
        settings.validate()
        if (
            settings.exposure_s
            < self._preset_options[settings.preset]["minimum_exposure_s"]
        ):
            raise ValueError("Exposure is below the selected detector preset minimum")
        return settings

    def _dark_validity(self) -> str:
        dark = self.pre_taken_dark
        if dark is None:
            return "No validated reusable dark. Capture a new NPZ dark."
        try:
            dark.validate_for(self._snapshot_settings())
        except ValueError:
            return "Stored dark is STALE for these settings; recapture before reuse."
        return f"Reusable dark valid for requested settings ({dark.record_id})."

    def _update_background_controls(self, *_args) -> None:
        enabled = self.use_background.isChecked()
        pre = self.background_mode.currentText() == "Use pre-taken stitched dark"
        self.background_mode.setEnabled(enabled)
        self.load_dark_button.setEnabled(
            not self._spectrometer_busy and enabled and pre
        )
        self.background_timing.setEnabled(enabled and not pre)
        self.clear_dark_button.setEnabled(
            not self._spectrometer_busy and self.pre_taken_dark is not None
        )
        validity = self._dark_validity()
        if not enabled:
            text = "Dark subtraction disabled; stored dark retained. " + validity
        elif pre:
            text = validity
        elif self.background_timing.currentIndex() == 0:
            text = "One dark per centre wavelength. " + validity
        else:
            text = "One dark per repeated frame. " + validity
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
    def request_stop(self) -> None:
        self._cancel_event.set()
        self.stop_button.setEnabled(False)
        self.set_status(
            "Cancellation requested; waiting for acquisition and disconnect cleanup."
        )

    def _run_async(self, coroutine_factory, on_done, on_error) -> None:
        if self._async_tasks:
            raise RuntimeError("Previous spectrum worker has not finished")
        self._cancel_event.clear()
        thread = QThread(self)
        runner = AsyncTaskRunner(coroutine_factory)
        task = (thread, runner)
        self._async_tasks.append(task)
        runner.moveToThread(thread)
        thread.started.connect(runner.run)
        runner.finished.connect(on_done)
        runner.failed.connect(on_error)
        runner.cancelled.connect(self._handle_cancelled)
        for signal in (runner.finished, runner.failed, runner.cancelled):
            signal.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(runner.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._thread_finished(task))
        thread.start()

    def _thread_finished(self, task) -> None:
        if task in self._async_tasks:
            self._async_tasks.remove(task)
        self._set_spectrometer_busy(False)
        self._update_background_controls()

    def _handle_cancelled(self) -> None:
        self.set_status("Spectrum operation cancelled; backend cleanup completed.")

    def _start_operation(self, factory, done, error, message) -> None:
        self._set_spectrometer_busy(True)
        self.set_status(message)
        try:
            self._run_async(factory, done, error)
        except Exception:
            self._set_spectrometer_busy(False)
            raise
        self._update_spectrometer_buttons()

    def test_spectrometer_connection(self) -> None:
        """Use the configured backend context; no second acquisition implementation."""
        if self._spectrometer_busy:
            return
        try:
            settings = self._snapshot_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return

        async def test():
            await self._service.test_connection(
                settings, cancel_requested=self._cancel_event.is_set
            )
            return settings.preset

        self._start_operation(
            test,
            self._handle_connection_test_done,
            self._handle_connection_error,
            "Testing spectrometer connection...",
        )

    def _handle_connection_test_done(self, preset) -> None:
        self.set_status(
            f"Spectrometer {preset} connected, configured and disconnected."
        )

    def _handle_connection_error(self, error) -> None:
        self.set_status("Connection test failed: " + self._exception_summary(error))
        self._show_error(
            "Spectrometer connection failed", self._exception_summary(error), error
        )

    def acquire_spectrum(self) -> None:
        if self._spectrometer_busy:
            return
        try:
            settings = self._snapshot_settings()
            mode = self._selected_dark_mode()
            dark = self.pre_taken_dark if mode == "pre_taken" else None
            if mode == "pre_taken":
                if dark is None:
                    raise ValueError(
                        "Capture or load a provenance-bearing NPZ dark first; legacy CSV cannot be validated."
                    )
                dark.validate_for(settings)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid spectrum settings or dark", str(exc))
            return
        self._save_options = (
            self.save_csv.isChecked(),
            self.save_png.isChecked(),
            self._selected_output_directory(),
        )
        self._start_operation(
            lambda: self._service.acquire(
                settings,
                dark_mode=mode,
                dark=dark,
                cancel_requested=self._cancel_event.is_set,
            ),
            self._handle_acquire_done,
            self._handle_acquire_error,
            f"Acquiring {settings.start_nm:.2f}-{settings.end_nm:.2f} nm ({mode})...",
        )

    def _handle_acquire_done(self, result: SpectrumResult) -> None:
        self.latest_result = result
        x_data, y_data = result.wavelength_nm, result.intensity
        self.ax.clear()
        identity = "Raw" if result.dark_mode == "none" else "Dark-corrected"
        self.ax.plot(x_data, y_data, color="#0b6fa4", linewidth=1.35, label=identity)
        self.ax.set_xlabel("Wavelength (nm)", fontsize=11)
        self.ax.set_ylabel("Intensity (counts)", fontsize=11)
        self.ax.set_title(
            f"HORIBA range spectrum ({identity.lower()})", fontsize=14, pad=12
        )
        self.ax.grid(True, color="#d9e2ec", linewidth=0.8, alpha=0.85)
        self.ax.set_facecolor("#fbfcfd")
        self.ax.margins(x=0.01, y=0.08)
        self.figure.tight_layout()
        self.canvas.draw_idle()
        self.plot_meta.setText(
            f"{x_data[0]:.2f}-{x_data[-1]:.2f} nm | {len(x_data)} points | {identity}"
        )
        try:
            saved = self._maybe_save_result(result)
        except Exception as exc:  # noqa: BLE001 - GUI boundary reports save failures
            self.set_status(f"Acquisition succeeded, but saving failed: {exc}")
            self._show_error("Save failed", str(exc), traceback.format_exc())
            return
        self.set_status(
            f"{identity} spectrum acquired." + (f" Saved to {saved}." if saved else "")
        )

    def _handle_acquire_error(self, error: str) -> None:
        summary = self._exception_summary(error)
        self.set_status("Acquisition failed: " + summary)
        self._show_error("Acquisition failed", summary, error)

    def capture_reusable_dark(self) -> None:
        if self._spectrometer_busy:
            return
        try:
            settings = self._snapshot_settings()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid dark settings", str(exc))
            return
        self._start_operation(
            lambda: self._service.capture_dark(
                settings, cancel_requested=self._cancel_event.is_set
            ),
            self._handle_dark_capture_done,
            self._handle_dark_capture_error,
            "Capturing provenance-bearing reusable dark...",
        )

    def _handle_dark_capture_done(self, dark: DarkRecord) -> None:
        self.pre_taken_dark = dark
        self._update_background_controls()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save reusable dark",
            str(self._selected_output_directory() / "range_dark.npz"),
            "NPZ dark archives (*.npz)",
        )
        if path:
            try:
                save_dark_record(Path(path).with_suffix(".npz"), dark)
                self.set_status(
                    f"Reusable dark saved to {path}; enable subtraction when needed."
                )
            except Exception as exc:  # noqa: BLE001 - GUI boundary reports save failures
                self._show_error("Save dark failed", str(exc), traceback.format_exc())
        else:
            self.set_status(
                "Reusable dark captured in memory; subtraction enablement unchanged."
            )

    def _handle_dark_capture_error(self, error: str) -> None:
        self.set_status("Dark capture failed: " + self._exception_summary(error))
        self._show_error("Dark capture failed", self._exception_summary(error), error)

    def load_pre_taken_dark(self) -> None:
        if self._spectrometer_busy:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load reusable dark",
            str(self._selected_output_directory()),
            "Validated NPZ darks (*.npz);;Legacy CSV (unverified) (*.csv)",
        )
        if not path:
            return
        if Path(path).suffix.lower() == ".csv":
            QMessageBox.warning(
                self,
                "Legacy dark unverified",
                "Legacy CSV has no acquisition settings or configuration provenance. "
                "It cannot be used for validated subtraction. Recapture a dark and save it as NPZ.",
            )
            self.set_status(
                "Legacy CSV not loaded for subtraction; recapture required."
            )
            return
        try:
            dark = load_dark_record(path)
        except Exception as exc:  # noqa: BLE001 - GUI boundary reports archive failures
            self._show_error("Load dark failed", str(exc), traceback.format_exc())
            return
        self.pre_taken_dark = dark
        self._update_background_controls()
        self.set_status("Dark archive loaded. " + self._dark_validity())

    def clear_pre_taken_dark(self) -> None:
        if self._spectrometer_busy:
            return
        self.pre_taken_dark = None
        self._update_background_controls()
        self.set_status("Cleared reusable dark.")

    def _maybe_save_result(self, result: SpectrumResult) -> Path | None:
        options = self._save_options
        if options is None or not any(options[:2]):
            return None
        csv_enabled, png_enabled, output_dir = options
        output_dir.mkdir(parents=True, exist_ok=True)
        base = f"horiba_{result.settings.start_nm:.0f}_{result.settings.end_nm:.0f}nm"
        stem = base
        suffix = 1
        while any(
            (output_dir / f"{stem}{extension}").exists()
            for extension in (".npz", ".csv", ".png")
        ):
            suffix += 1
            stem = f"{base}_{suffix}"
        # The immutable result is the sole source for arrays and acquisition metadata.
        save_spectrum_result(output_dir / f"{stem}.npz", result)
        if csv_enabled:
            with (output_dir / f"{stem}.csv").open(
                "x", newline="", encoding="utf-8"
            ) as handle:
                writer = csv.writer(handle)
                writer.writerow(["wavelength_nm", "intensity"])
                writer.writerows(
                    zip(result.wavelength_nm, result.intensity, strict=True)
                )
        if png_enabled:
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
        if self._spectrometer_busy or self._async_tasks:
            self.request_stop()
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
    configuration_id = os.environ.get("LABTOOLS_SPECTRUM_CONFIGURATION_ID")
    if not configuration_id:
        QMessageBox.critical(
            None,
            "Spectrum configuration missing",
            "A maintainer must set LABTOOLS_SPECTRUM_CONFIGURATION_ID before launching this tool.",
        )
        raise SystemExit(2)
    window = HoribaRangeWindow(configuration_id=configuration_id)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
