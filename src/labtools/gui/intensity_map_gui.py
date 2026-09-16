"""PyQt6 GUI for resumable intensity maps and ITC4000 laser control."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.colors import LogNorm, Normalize
from matplotlib.figure import Figure
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
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
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QToolButton,
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
from labtools.devices.itc4000 import ITC4000
from labtools.visualisation.intensity_map import update_map_axes

MAX_LASER_CURRENT_A = 0.100
DEFAULT_LASER_CURRENT_A = 0.080
LASER_THRESHOLD_CURRENT_A = 0.049
DEFAULT_OUTPUT_ROOT = Path("C:/LabData/IntensityMaps")


class MapWorker(QObject):
    """Run blocking intensity-map acquisition outside the Qt main thread."""

    progress = pyqtSignal(object)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str, str)

    def __init__(
        self,
        config: IntensityMapConfig,
        resume_directory: Path | None,
    ) -> None:
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

    def cancel(self) -> None:
        self._cancel = True


class IntensityMapWindow(QMainWindow):
    """Main window for live count maps, resume, and laser control."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Intensity Map Acquisition")
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)
        self._thread: QThread | None = None
        self._worker: MapWorker | None = None
        self._resume_directory: Path | None = None
        self._latest_plot_values: np.ndarray | None = None
        self.laser: ITC4000 | None = None
        self._apply_application_style()

        central = QWidget(self)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title_column = QVBoxLayout()
        title = QLabel("Intensity Map Acquisition")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Configure the scanning mirror and Time Controller, acquire "
            "resumable maps, and control the excitation laser"
        )
        subtitle.setObjectName("pageSubtitle")
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        header.addLayout(title_column)
        header.addStretch(1)
        self.laser_light = QLabel("Laser output: OFF")
        self.laser_light.setMinimumSize(170, 34)
        self.laser_light.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.laser_light, 0, Qt.AlignmentFlag.AlignTop)
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
        controls_scroll.setMinimumWidth(430)
        controls_scroll.setMaximumWidth(500)
        controls = QWidget()
        controls.setMinimumWidth(410)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(8, 0, 8, 8)
        controls_layout.setSpacing(12)
        self._build_map_controls(controls_layout)
        self._build_laser_controls(controls_layout)
        self._build_persistent_acquisition_controls(controls_layout)
        controls_layout.addStretch(1)
        controls_scroll.setWidget(controls)
        splitter.addWidget(controls_scroll)

        plot_panel = QFrame()
        plot_panel.setObjectName("plotPanel")
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(14, 12, 14, 12)
        plot_layout.setSpacing(8)
        plot_header = QHBoxLayout()
        plot_title = QLabel("Intensity map")
        plot_title.setObjectName("sectionTitle")
        self.plot_meta = QLabel("No map acquired")
        self.plot_meta.setObjectName("plotMeta")
        plot_header.addWidget(plot_title)
        plot_header.addStretch(1)
        plot_header.addWidget(self.plot_meta)
        plot_layout.addLayout(plot_header)

        self.figure = Figure(figsize=(10, 7), dpi=100)
        self.figure.set_facecolor("#ffffff")
        self.axes = self.figure.add_subplot(111)
        self._style_empty_axes()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.canvas.setMinimumHeight(430)
        self.toolbar = NavigationToolbar(self.canvas, self)
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self._build_plot_colour_controls())
        plot_layout.addWidget(self.canvas, 1)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        plot_layout.addWidget(self.progress)
        splitter.addWidget(plot_panel)
        splitter.setSizes([465, 975])

        self.status = QLabel("Ready")
        self.status.setObjectName("statusText")
        self.status.setWordWrap(True)
        self.statusBar().addWidget(self.status, 1)
        self._toggle_laser_controls(False)
        self._update_estimate()

    def _apply_application_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f3f5f7; }
            QWidget { color: #17212b; font-size: 12px; }
            QLabel#pageTitle { font-size: 25px; font-weight: 700; color: #102a43; }
            QLabel#pageSubtitle { color: #627d98; font-size: 13px; }
            QLabel#sectionTitle { font-size: 17px; font-weight: 700; color: #102a43; }
            QLabel#plotMeta, QLabel#hintText { color: #627d98; }
            QLabel#statusText { color: #334e68; padding: 4px 8px; }
            QFrame#plotPanel, QFrame#persistentControls, QGroupBox {
                background: #ffffff; border: 1px solid #d9e2ec; border-radius: 8px;
            }
            QFrame#plotColourControls {
                background: #f7fafc; border: 1px solid #d9e2ec; border-radius: 6px;
            }
            QGroupBox { margin-top: 0px; padding: 7px 8px 8px 8px; }
            QToolButton#sectionToggle {
                border: none; background: transparent; color: #243b53;
                font-weight: 650; padding: 1px 2px; text-align: left;
            }
            QToolButton#sectionToggle:hover { color: #0b6fa4; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                min-height: 27px; padding: 1px 5px; background: #ffffff;
                border: 1px solid #bcccdc; border-radius: 5px;
                selection-background-color: #2680c2;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
            QDoubleSpinBox:focus { border: 2px solid #2680c2; }
            QPushButton {
                min-height: 29px; padding: 3px 9px; background: #ffffff;
                border: 1px solid #9fb3c8; border-radius: 5px; color: #243b53;
            }
            QPushButton:hover { background: #f0f4f8; }
            QPushButton:disabled { background: #f0f4f8; color: #9fb3c8; }
            QPushButton#primaryButton {
                min-height: 39px; background: #0b6fa4; border-color: #0b6fa4;
                color: white; font-weight: 700;
            }
            QPushButton#dangerButton { color: #b42318; border-color: #f0b4ae; }
            QCheckBox { spacing: 7px; }
            QProgressBar {
                min-height: 18px; border: 1px solid #bcccdc;
                border-radius: 5px; text-align: center;
            }
            QProgressBar::chunk { background: #0b6fa4; border-radius: 4px; }
            QScrollArea { background: transparent; }
            QSplitter::handle { background: transparent; }
            QStatusBar { background: #ffffff; border-top: 1px solid #d9e2ec; }
            """
        )

    def _build_plot_colour_controls(self) -> QWidget:
        """Build compact live-plot colour controls above the plot."""
        panel = QFrame()
        panel.setObjectName("plotColourControls")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(10)

        self.log_colour_scale = QCheckBox("Log colour scale")
        self.log_colour_scale.toggled.connect(self._refresh_colour_scale)
        layout.addWidget(self.log_colour_scale)

        self.custom_colour_limits = QCheckBox("Manual limits")
        self.custom_colour_limits.toggled.connect(self._toggle_colour_limit_controls)
        layout.addWidget(self.custom_colour_limits)

        self.colour_limits_widget = QWidget()
        limits_layout = QHBoxLayout(self.colour_limits_widget)
        limits_layout.setContentsMargins(0, 0, 0, 0)
        limits_layout.setSpacing(6)
        self.colour_min = QDoubleSpinBox()
        self.colour_max = QDoubleSpinBox()
        for box in (self.colour_min, self.colour_max):
            box.setRange(0.0, 1.0e15)
            box.setDecimals(3)
            box.setSingleStep(100.0)
            box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            box.setMinimumWidth(105)
            box.valueChanged.connect(self._refresh_colour_scale)
        self.colour_min.setValue(0.0)
        self.colour_max.setValue(1000.0)
        limits_layout.addWidget(QLabel("Lower"))
        limits_layout.addWidget(self.colour_min)
        limits_layout.addWidget(QLabel("Upper"))
        limits_layout.addWidget(self.colour_max)
        layout.addWidget(self.colour_limits_widget)
        layout.addStretch(1)
        self.colour_limits_widget.setVisible(False)
        return panel

    def _style_empty_axes(self) -> None:
        self.axes.clear()
        self.image = self.axes.imshow(
            np.full((2, 2), np.nan),
            origin="lower",
            aspect="auto",
            interpolation="nearest",
            cmap="inferno",
            extent=(0, 1, 0, 1),
        )
        self.colourbar = self.figure.colorbar(self.image, ax=self.axes, pad=0.03)
        self.colourbar.set_label("Count rate (counts s$^{-1}$)")
        self.axes.set_xlabel("Mirror X voltage (V)", fontsize=11)
        self.axes.set_ylabel("Mirror Y voltage (V)", fontsize=11)
        self.axes.set_title("Ready for acquisition", fontsize=13, pad=12)
        self.axes.set_facecolor("#fbfcfd")
        self.figure.subplots_adjust(left=0.15, right=0.87, bottom=0.13, top=0.90)

    def _build_map_controls(self, root: QVBoxLayout) -> None:
        scan = QGroupBox("Map setup")
        form = QFormLayout(scan)
        form.setVerticalSpacing(9)
        self.x_start, self.x_stop, self.x_points = self._axis_controls(-2.2, -1.8, 3)
        self.y_start, self.y_stop, self.y_points = self._axis_controls(-0.7, -0.3, 3)
        form.addRow(
            "X range", self._axis_widget(self.x_start, self.x_stop, self.x_points)
        )
        form.addRow(
            "Y range", self._axis_widget(self.y_start, self.y_stop, self.y_points)
        )
        self.settle = QDoubleSpinBox()
        self.settle.setRange(0.0, 10.0)
        self.settle.setDecimals(3)
        self.settle.setValue(0.010)
        self.settle.setSuffix(" s")
        form.addRow("Mirror settle time", self.settle)
        self.serpentine = QCheckBox("Use serpentine scan order")
        self.serpentine.setChecked(True)
        form.addRow("", self.serpentine)
        path_widget = QWidget()
        path_layout = QHBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)
        self.output_root = QLineEdit(str(DEFAULT_OUTPUT_ROOT))
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._choose_output)
        path_layout.addWidget(self.output_root, 1)
        path_layout.addWidget(browse)
        form.addRow("Output folder", path_widget)
        self.save_results = QCheckBox("Save completed datasets and plot")
        self.save_results.setChecked(True)
        self.save_results.toggled.connect(self._update_estimate)
        form.addRow("", self.save_results)
        root.addWidget(scan)
        self._make_collapsible(scan, initially_open=False)

        tc = QGroupBox("Time Controller")
        tc_form = QFormLayout(tc)
        tc_form.setVerticalSpacing(9)
        self.address = QLineEdit("169.254.99.159")
        self.integration = QDoubleSpinBox()
        self.integration.setRange(0.001, 3600.0)
        self.integration.setDecimals(3)
        self.integration.setValue(0.100)
        self.integration.setSuffix(" s")
        self.channel_1 = QComboBox()
        self.channel_1.addItems(["1", "2", "3", "4"])
        self.threshold_1 = self._threshold_box(0.1)
        self.edge_1 = QComboBox()
        self.edge_1.addItems(["Rising", "Falling"])
        self.use_second = QCheckBox("Acquire a second channel and plot the sum")
        self.channel_2 = QComboBox()
        self.channel_2.addItems(["1", "2", "3", "4"])
        self.channel_2.setCurrentText("2")
        self.threshold_2 = self._threshold_box(0.1)
        self.edge_2 = QComboBox()
        self.edge_2.addItems(["Rising", "Falling"])
        self.second_channel_widget = self._channel_settings_widget(
            self.channel_2,
            self.threshold_2,
            self.edge_2,
        )
        self.second_channel_label = QLabel("Second channel")
        tc_form.addRow("IP address", self.address)
        tc_form.addRow("Integration time", self.integration)
        tc_form.addRow(
            "Primary channel",
            self._channel_settings_widget(
                self.channel_1,
                self.threshold_1,
                self.edge_1,
            ),
        )
        tc_form.addRow("", self.use_second)
        tc_form.addRow(self.second_channel_label, self.second_channel_widget)
        self.use_second.toggled.connect(self._sync_second_channel_visibility)
        self._sync_second_channel_visibility(False)
        hint = QLabel(
            "Each selected channel is saved separately; two-channel maps "
            "display their summed count rate."
        )
        hint.setObjectName("hintText")
        hint.setWordWrap(True)
        tc_form.addRow("", hint)
        self.time_controller_group = tc
        root.addWidget(tc)
        self.time_controller_toggle = self._make_collapsible(tc, initially_open=False)
        self.time_controller_toggle.toggled.connect(
            lambda _expanded: self._sync_second_channel_visibility()
        )

        self.start_button = QPushButton("Start new map")
        self.start_button.setObjectName("primaryButton")
        self.resume_button = QPushButton("Resume map...")
        self.stop_button = QPushButton("Stop after current point")
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_new)
        self.resume_button.clicked.connect(self.choose_resume)
        self.stop_button.clicked.connect(self.request_stop)
        for box in (
            self.x_start,
            self.x_stop,
            self.x_points,
            self.y_start,
            self.y_stop,
            self.y_points,
            self.settle,
            self.integration,
        ):
            box.valueChanged.connect(self._update_estimate)

    def _build_laser_controls(self, root: QVBoxLayout) -> None:
        self.laser_group = QGroupBox("Laser control")
        form = QFormLayout(self.laser_group)
        form.setVerticalSpacing(9)
        self.laser_address = QLineEdit(ITC4000.DEFAULT_ADDRESS)
        self.laser_current = QDoubleSpinBox()
        self.laser_current.setRange(0.0, MAX_LASER_CURRENT_A)
        self.laser_current.setDecimals(3)
        self.laser_current.setSingleStep(0.001)
        self.laser_current.setValue(DEFAULT_LASER_CURRENT_A)
        self.laser_current.setSuffix(" A")
        self.set_laser_indicator(False)
        form.addRow("VISA address", self.laser_address)
        form.addRow("Drive current", self.laser_current)
        self.laser_connect = QPushButton("Connect")
        self.laser_set = QPushButton("Apply current")
        self.laser_on = QPushButton("Output ON")
        self.laser_off = QPushButton("Output OFF")
        grid = QGridLayout()
        grid.addWidget(self.laser_connect, 0, 0)
        grid.addWidget(self.laser_set, 0, 1)
        grid.addWidget(self.laser_on, 1, 0)
        grid.addWidget(self.laser_off, 1, 1)
        form.addRow(grid)
        root.addWidget(self.laser_group)
        self.laser_toggle = self._make_collapsible(
            self.laser_group,
            initially_open=False,
        )
        self.laser_toggle.toggled.connect(self._toggle_laser_controls)
        self.laser_connect.clicked.connect(self.connect_laser)
        self.laser_set.clicked.connect(self.set_laser_current)
        self.laser_on.clicked.connect(self.turn_laser_on)
        self.laser_off.clicked.connect(self.turn_laser_off)

    def _sync_second_channel_visibility(self, checked: bool | None = None) -> None:
        enabled = self.use_second.isChecked() if checked is None else checked
        section_open = (
            not hasattr(self, "time_controller_toggle")
            or self.time_controller_toggle.isChecked()
        )
        visible = enabled and section_open
        self.second_channel_label.setVisible(visible)
        self.second_channel_widget.setVisible(visible)

    def _build_persistent_acquisition_controls(self, root: QVBoxLayout) -> None:
        panel = QFrame()
        panel.setObjectName("persistentControls")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(7)
        self.estimate = QLabel()
        self.estimate.setObjectName("hintText")
        layout.addWidget(self.estimate)
        layout.addWidget(self.start_button)
        row = QHBoxLayout()
        row.addWidget(self.resume_button)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        root.addWidget(panel)

    def _make_collapsible(
        self,
        group: QGroupBox,
        *,
        initially_open: bool,
    ) -> QToolButton:
        title = group.title()
        group.setTitle("")
        group.setCheckable(False)
        layout = group.layout()
        if not isinstance(layout, QFormLayout):
            raise TypeError("Collapsible sections require a QFormLayout.")
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
            if group is getattr(self, "time_controller_group", None):
                self._sync_second_channel_visibility()
            group.adjustSize()
            group.updateGeometry()

        toggle.toggled.connect(set_expanded)
        set_expanded(initially_open)
        return toggle

    @staticmethod
    def _threshold_box(value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(-5.0, 5.0)
        box.setDecimals(3)
        box.setSingleStep(0.01)
        box.setValue(value)
        box.setSuffix(" V")
        box.setMinimumWidth(85)
        return box

    @staticmethod
    def _channel_settings_widget(
        channel: QWidget, threshold: QWidget, edge: QWidget
    ) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(6)
        for column, (label, control) in enumerate(
            (("Channel", channel), ("Threshold", threshold), ("Slope", edge))
        ):
            layout.addWidget(QLabel(label), 0, column)
            layout.addWidget(control, 1, column)
        return widget

    @staticmethod
    def _axis_controls(
        start: float, stop: float, points: int
    ) -> tuple[QDoubleSpinBox, QDoubleSpinBox, QSpinBox]:
        start_box = QDoubleSpinBox()
        stop_box = QDoubleSpinBox()
        points_box = QSpinBox()
        for box, value in ((start_box, start), (stop_box, stop)):
            box.setRange(-10.0, 10.0)
            box.setDecimals(4)
            box.setValue(value)
            box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            box.setAlignment(Qt.AlignmentFlag.AlignRight)
            box.setMinimumWidth(100)
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        points_box.setRange(2, 10000)
        points_box.setValue(points)
        points_box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        points_box.setAlignment(Qt.AlignmentFlag.AlignRight)
        points_box.setMinimumWidth(82)
        points_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return start_box, stop_box, points_box

    @staticmethod
    def _axis_widget(start: QWidget, stop: QWidget, points: QWidget) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        for column, (label, control) in enumerate(
            (("Start (V)", start), ("Stop (V)", stop), ("Points", points))
        ):
            layout.addWidget(QLabel(label), 0, column)
            layout.addWidget(control, 1, column)
            layout.setColumnStretch(column, 1)
        layout.setColumnMinimumWidth(0, 100)
        layout.setColumnMinimumWidth(1, 100)
        layout.setColumnMinimumWidth(2, 82)
        return widget

    def _toggle_colour_limit_controls(self, enabled: bool) -> None:
        self.colour_limits_widget.setVisible(enabled)
        self._refresh_colour_scale()

    def _refresh_colour_scale(self, _value: object = None) -> None:
        if self._latest_plot_values is None:
            values = np.asarray(self.image.get_array(), dtype=float)
        else:
            values = np.asarray(self._latest_plot_values, dtype=float)
        finite = values[np.isfinite(values)]
        positive = finite[finite > 0.0]
        use_log = self.log_colour_scale.isChecked()

        if self.custom_colour_limits.isChecked():
            lower = float(self.colour_min.value())
            upper = float(self.colour_max.value())
            if upper <= lower:
                self.set_status("Colour-scale upper limit must exceed the lower limit.")
                return
            if use_log and lower <= 0.0:
                self.set_status("Log colour scales require a positive lower limit.")
                return
        elif use_log:
            if positive.size:
                lower = float(np.min(positive))
                upper = float(np.max(positive))
                if np.isclose(lower, upper):
                    upper = lower * 10.0
            else:
                lower, upper = 1.0, 10.0
        elif finite.size:
            lower = float(np.min(finite))
            upper = float(np.max(finite))
            if np.isclose(lower, upper):
                upper = lower + max(1.0, abs(lower) * 0.01)
        else:
            lower, upper = 0.0, 1.0

        display_values = np.ma.masked_less_equal(values, 0.0) if use_log else values
        self.image.set_data(display_values)
        if use_log:
            self.image.set_norm(LogNorm(vmin=lower, vmax=upper, clip=True))
        else:
            self.image.set_norm(Normalize(vmin=lower, vmax=upper, clip=True))
        self.colourbar.update_normal(self.image)
        self.canvas.draw_idle()

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def _channels(self) -> tuple[int, ...]:
        first = int(self.channel_1.currentText())
        if self.use_second.isChecked():
            return first, int(self.channel_2.currentText())
        return (first,)

    def _thresholds(self) -> tuple[float, ...]:
        first = float(self.threshold_1.value())
        if self.use_second.isChecked():
            return first, float(self.threshold_2.value())
        return (first,)

    def _edges(self) -> tuple[str, ...]:
        first = self.edge_1.currentText().lower()
        if self.use_second.isChecked():
            return first, self.edge_2.currentText().lower()
        return (first,)

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
            channel_thresholds_v=self._thresholds(),
            channel_edges=self._edges(),
            settle_time_s=self.settle.value(),
            time_controller_address=self.address.text().strip(),
            serpentine=self.serpentine.isChecked(),
            output_root=Path(self.output_root.text().strip()),
            save_results=self.save_results.isChecked(),
        )

    def _apply_config(self, config: IntensityMapConfig) -> None:
        for control, value in (
            (self.x_start, config.x_start_v),
            (self.x_stop, config.x_stop_v),
            (self.y_start, config.y_start_v),
            (self.y_stop, config.y_stop_v),
            (self.integration, config.integration_time_s),
            (self.settle, config.settle_time_s),
        ):
            control.setValue(value)
        self.x_points.setValue(config.x_points)
        self.y_points.setValue(config.y_points)
        self.address.setText(config.time_controller_address)
        self.channel_1.setCurrentText(str(config.channels[0]))
        self.threshold_1.setValue(config.channel_thresholds_v[0])
        self.edge_1.setCurrentText(config.channel_edges[0].title())
        self.use_second.setChecked(len(config.channels) == 2)
        if len(config.channels) == 2:
            self.channel_2.setCurrentText(str(config.channels[1]))
            self.threshold_2.setValue(config.channel_thresholds_v[1])
            self.edge_2.setCurrentText(config.channel_edges[1].title())
        self.serpentine.setChecked(config.serpentine)
        self.output_root.setText(str(config.output_root))
        self.save_results.setChecked(config.save_results)

    def _update_estimate(self) -> None:
        try:
            seconds = estimated_minimum_duration_s(self._config())
        except (AttributeError, ValueError):
            return
        save_text = (
            "saving enabled"
            if self.save_results.isChecked()
            else "final saving disabled"
        )
        self.estimate.setText(
            f"Estimated minimum: {seconds:.1f} s plus overhead | {save_text}"
        )

    def _choose_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select map output folder",
            self.output_root.text(),
        )
        if selected:
            self.output_root.setText(selected)

    def start_new(self) -> None:
        self._resume_directory = None
        self._start_worker(self._config())

    def choose_resume(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select incomplete map directory",
            self.output_root.text(),
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
        if len(config.channels) == 2 and config.channels[0] == config.channels[1]:
            QMessageBox.warning(
                self,
                "Invalid channels",
                "Select two different Time Controller channels.",
            )
            return
        self.start_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress.setValue(0)
        self.set_status("Starting acquisition...")
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
        self.set_status("Stopping after the current point and saving checkpoint...")
        if self._worker is not None:
            self._worker.cancel()

    @pyqtSlot(object)
    def _on_progress(self, snapshot: IntensityMapSnapshot) -> None:
        self.progress.setValue(
            int(100 * snapshot.points_complete / snapshot.total_points)
        )
        title = (
            f"Channels {' + '.join(map(str, snapshot.channels))}: "
            f"{snapshot.points_complete}/{snapshot.total_points}"
        )
        values = np.asarray(snapshot.summed_count_rate_cps, dtype=float)
        if self.image.get_array().shape != values.shape:
            self.colourbar.remove()
            self.axes.clear()
            self.image = self.axes.imshow(
                values,
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
            self.colourbar = self.figure.colorbar(self.image, ax=self.axes, pad=0.03)
            self.colourbar.set_label("Count rate (counts s$^{-1}$)")
            self.figure.subplots_adjust(
                left=0.15,
                right=0.87,
                bottom=0.13,
                top=0.90,
            )
        self._latest_plot_values = values.copy()
        update_map_axes(self.axes, self.image, values, title=title)
        self.axes.set_facecolor("#fbfcfd")
        self._refresh_colour_scale()
        self.plot_meta.setText(
            f"{snapshot.points_complete}/{snapshot.total_points} points"
        )
        self.set_status(
            f"Elapsed: {snapshot.elapsed_s:.1f} s | Output: {snapshot.output_directory}"
        )

    @pyqtSlot(object)
    def _on_finished(self, result: Any) -> None:
        text = "completed" if result.complete else "stopped with checkpoint saved"
        self.set_status(f"Map {text}. Output: {result.output_directory}")
        if result.complete:
            self.progress.setValue(100)

    @pyqtSlot(str, str)
    def _on_failed(self, message: str, details: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Intensity-map acquisition failed")
        box.setText(message)
        box.setDetailedText(details)
        box.exec()
        self.set_status("Acquisition failed. Partial checkpoint was retained.")

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

    def set_laser_indicator(self, on: bool) -> None:
        if on:
            text, colour, border = "Laser output: ON", "#1f5a2a", "#5fd17a"
        else:
            text, colour, border = "Laser output: OFF", "#3a3a3a", "#666666"
        self.laser_light.setText(text)
        self.laser_light.setStyleSheet(
            f"QLabel {{ background-color: {colour}; color: white; "
            f"border: 1px solid {border}; border-radius: 8px; padding: 6px; }}"
        )

    def _toggle_laser_controls(self, enabled: bool) -> None:
        connected = self.laser is not None
        self.laser_address.setEnabled(enabled and not connected)
        self.laser_current.setEnabled(enabled)
        self.laser_connect.setEnabled(enabled)
        self.laser_on.setEnabled(enabled and connected)
        self.laser_off.setEnabled(enabled and connected)
        self.laser_set.setEnabled(enabled and connected)

    def _laser_error(self, title: str, exc: Exception) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(str(exc))
        box.setDetailedText(traceback.format_exc())
        box.exec()

    def connect_laser(self) -> None:
        address = self.laser_address.text().strip() or ITC4000.DEFAULT_ADDRESS
        self.set_status(f"Connecting to laser at {address}...")
        try:
            if self.laser is not None:
                self.laser.close()
            laser = ITC4000(
                address,
                threshold_current=LASER_THRESHOLD_CURRENT_A,
                max_current=MAX_LASER_CURRENT_A,
            )
            identity = laser.identify()
            current = laser.get_current()
            diode_on = laser.get_diode_output()
            tec_on = laser.get_tec_output()
            self.laser = laser
            self.laser_current.setValue(current)
            self.set_laser_indicator(diode_on)
            self._toggle_laser_controls(True)
            self.set_status(
                f"Connected: {identity} | Current: {current:.3f} A | "
                f"LD: {'ON' if diode_on else 'OFF'} | "
                f"TEC: {'ON' if tec_on else 'OFF'}"
            )
        except Exception as exc:  # noqa: BLE001
            self.laser = None
            self.set_laser_indicator(False)
            self._toggle_laser_controls(True)
            self._laser_error("Laser connection failed", exc)

    def turn_laser_on(self) -> None:
        if self.laser is None:
            QMessageBox.warning(self, "No laser", "Connect the laser first.")
            return
        try:
            self.laser.enable(current=float(self.laser_current.value()))
            on = self.laser.get_diode_output()
            current = self.laser.get_current()
            self.set_laser_indicator(on)
            self.set_status(
                f"Laser output {'ON' if on else 'OFF'}; current {current:.3f} A."
            )
        except Exception as exc:  # noqa: BLE001
            self.set_laser_indicator(False)
            self._laser_error("Laser enable failed", exc)

    def turn_laser_off(self) -> None:
        if self.laser is None:
            QMessageBox.warning(self, "No laser", "Connect the laser first.")
            return
        try:
            self.laser.disable()
            on = self.laser.get_diode_output()
            current = self.laser.get_current()
            self.laser_current.setValue(current)
            self.set_laser_indicator(on)
            self.set_status(
                f"Laser output {'ON' if on else 'OFF'}; current {current:.3f} A."
            )
        except Exception as exc:  # noqa: BLE001
            self._laser_error("Laser shutdown failed", exc)

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
            self._laser_error("Set current failed", exc)

    def closeEvent(self, event: Any) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.warning(
                self,
                "Acquisition in progress",
                "Stop the map and wait for checkpoint saving before closing.",
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
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = IntensityMapWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
