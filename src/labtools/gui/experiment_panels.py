"""Unified point-dose, hyperspectral and repeat-sequence operator panels."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import replace
from pathlib import Path
from threading import Event, Lock
from zipfile import BadZipFile

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from labtools.acquisition.spectrum_service import DarkRecord
from labtools.config.anneal_program import AnnealProgram
from labtools.config.hyperspectral import HyperspectralConfig
from labtools.gui.workspace_studio import StudioSplit, add_card, scroll_content
from labtools.io.spectrum_records import load_dark_record, save_dark_record
from labtools.runtime.experiment_workflows import (
    capture_cube_dark,
    run_cube,
    run_program,
    run_sequence,
    unique_directory,
    validate_cube,
)
from labtools.runtime.workflow_batch import Batch
from labtools.visualisation.intensity_map import MIRROR_Y_PER_X_SCALE


def number(value, lower=0.0, upper=43200.0, decimals=6):
    box = QDoubleSpinBox()
    box.setDecimals(decimals)
    box.setRange(lower, upper)
    box.setValue(value)
    return box


def integer(value, upper=10000):
    box = QSpinBox()
    box.setRange(1, upper)
    box.setValue(value)
    return box


class TaskPanel(QWidget):
    """One background task; GUI polling, cooperative Stop and no late lease release."""

    def __init__(self, workspace, title):
        super().__init__()
        self.workspace = workspace
        self.future = None
        self.executor = None
        self.batch = None
        self.stop_event = Event()
        self.last_result = None
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(0, 14, 0, 0)
        heading = QLabel(title)
        heading.setObjectName("studioTitle")
        self.layout_root.addWidget(heading)
        self.split = StudioSplit()
        self.layout_root.addWidget(self.split, 1)
        left = QWidget()
        self.left = QVBoxLayout(left)
        self.left.setContentsMargins(0, 0, 0, 0)
        scroll, self.controls = scroll_content()
        self.left.addWidget(scroll, 1)
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("primaryButton")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.save_result_button = QPushButton("Save results…")
        self.save_result_button.setEnabled(False)
        self.save_result_button.setToolTip("Save the retained run without reacquisition. Save before a replacement run or closing the application.")
        self.save_result_button.clicked.connect(self.save_retained)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        self.left.addLayout(buttons)
        self.left.addWidget(self.save_result_button)
        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        self.left.addWidget(self.status)
        self.split.addWidget(left)
        self.right = QWidget()
        self.results = QVBoxLayout(self.right)
        self.split.addWidget(self.right)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.results.addWidget(self.log)
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.poll)
        self.stop_button.clicked.connect(self.request_stop)
        self._message = ""
        self._display_lock = Lock()
        self._latest_display = None
        self.displayed_measurement = None

    @property
    def busy(self):
        return self.future is not None

    def report(self, text):
        # Bounded latest status, never touch widgets from a worker.
        self._message = str(text)

    def launch(self, function, owners=None):
        if self.busy:
            return
        self.stop_event = Event()
        self.last_result = None
        self.save_result_button.setEnabled(False)
        try:
            if owners:
                self.batch = Batch(self.workspace._ownership, owners)
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="labtools-experiment")
            self.future = self.executor.submit(copy_context().run, function)
        except BaseException:
            if self.batch is not None:
                self.batch.release()
                self.batch = None
            raise
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.timer.start()
        self.status.setText("Running; settings are snapshotted for this run")

    def request_stop(self):
        self.stop_event.set()
        self.stop_button.setEnabled(False)
        self.status.setText("Stopping after active operation and cleanup")

    def publish(self, kind, value):
        with self._display_lock:
            self._latest_display = (kind, value)

    def drain_display(self):
        with self._display_lock:
            latest, self._latest_display = self._latest_display, None
        if latest is not None:
            self.displayed_measurement = latest
            self.render_measurement(*latest)

    def render_measurement(self, kind, value):
        return None

    def poll(self):
        self.drain_display()
        if self._message:
            self.status.setText(self._message)
            self._message = ""
        if self.future is None or not self.future.done():
            return
        try:
            self.last_result = self.future.result()
            self.drain_display()
            self.completed(self.last_result)
        except asyncio.CancelledError:
            self.status.setText("Cancelled after cleanup")
        except Exception as error:  # noqa: BLE001 - terminal GUI worker boundary
            self.last_result = getattr(error, "retained_run", getattr(error, "partial_result", None))
            self.status.setText("Failed: " + str(error))
            self.log.appendPlainText(repr(error))
        finally:
            self.future = None
            self.executor.shutdown(wait=True)
            self.executor = None
            if self.batch is not None:
                self.batch.release()
                self.batch = None
            self.timer.stop()
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.save_result_button.setEnabled(self.last_result is not None)

    def save_retained(self):
        if self.busy or self.last_result is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Save retained experiment results")
        if folder:
            try:
                from labtools.runtime.retained_results import export_retained

                target = export_retained(folder, self.last_result, label=type(self).__name__, settings=getattr(self, "run_settings", None))
                self.status.setText("Saved retained run: " + str(target))
            except (OSError, ValueError, TypeError) as error:
                self.status.setText("Save failed; run remains retained: " + str(error))

    def completed(self, result):
        self.status.setText("Stopped" if self.stop_event.is_set() else "Completed")
        if isinstance(result, dict):
            self.log.appendPlainText(f"Status: {result.get('status', 'completed')} | Completed steps: {len(result.get('steps', []))} | Completed points: {result.get('completed_points', '-')}")
        else:
            self.log.appendPlainText("Acquisition completed; results retained in memory.")

    def closeEvent(self, event):
        if self.busy:
            self.request_stop()
            event.ignore()
        else:
            event.accept()


class AnnealProgramPanel(TaskPanel):
    def __init__(self, workspace, anneal_panel):
        super().__init__(workspace, "Annealing programs")
        self.anneal_panel = anneal_panel
        self.mode = QComboBox()
        self.mode.addItems(["Single point", "Dwell ramp array", "Uniform array"])
        self.first_dwell = number(0.001)
        self.last_dwell = number(0.01)
        self.spacing = QComboBox()
        self.spacing.addItems(["Linear", "Logarithmic"])
        add_card(self.controls, "Dose program", [("Mode", self.mode), ("First / single dwell (s)", self.first_dwell),
                 ("Last dwell (s)", self.last_dwell), ("Spacing", self.spacing)])
        note = QLabel("Coordinates, grid, passes, output and stage settings come from Annealing. Single point uses X start / Y start. Ramps follow traversal order, restarting each pass. Each point closes the shutter and completes stage/home cleanup before the next.")
        note.setWordWrap(True)
        self.controls.addWidget(note)
        self.preview_button = QPushButton("Preview point doses")
        self.controls.addWidget(self.preview_button)
        self.controls.addStretch(1)
        self.preview_button.clicked.connect(self.preview)
        self.start_button.clicked.connect(self.start)
        enabled = getattr(workspace, "simulation_only", False) or (getattr(workspace, "all_hardware_enabled", False) and workspace.drafts.profile_error is None)
        self.start_button.setEnabled(enabled)

    def snapshot(self):
        from labtools.gui.native_anneal_panel import CHECKS, NUMERIC

        panel = self.anneal_panel
        base = replace(self.workspace.drafts.anneal_base,
            **{field: getattr(panel, name).value() for field, name in NUMERIC.items() if field != "point_dwell_s"},
            **{field: getattr(panel, name).isChecked() for field, name in CHECKS.items()},
            output_root=Path(panel.output_root.text().strip()), point_dwell_s=self.first_dwell.value())
        if self.mode.currentText() == "Single point":
            base = replace(base, x_stop_v=base.x_start_v, y_stop_v=base.y_start_v, x_points=1, y_points=1)
        self.workspace.drafts.validate("anneal", base)
        program = AnnealProgram(base, self.mode.currentText(), self.last_dwell.value(), self.spacing.currentText())
        program.points()
        return program

    def preview(self):
        try:
            points = self.snapshot().points()
            lines = [f"{i+1}: X={p.x_start_v:g} V, Y={p.y_start_v:g} V, dwell={p.point_dwell_s:g} s" for i, p in enumerate(points[:1000])]
            self.log.setPlainText(f"{len(points)} point exposures\n" + "\n".join(lines))
        except (ValueError, RuntimeError) as error:
            self.status.setText(str(error))

    def start(self):
        try:
            program = self.snapshot()
            self.run_settings = program
            def run():
                with self.batch.borrow("Annealing"):
                    return run_program(self.workspace, program, stop=self.stop_event, report=self.report, save_output=program.base.save_run_log)
            self.launch(run, ("Annealing",))
        except (ValueError, RuntimeError) as error:
            self.status.setText(str(error))


def output_card(layout, output, browse, save=None):
    rows = [(None, save)] if save is not None else []
    rows += [(None, QLabel("Output folder")), (None, output), (None, browse)]
    card = add_card(layout, "Output", rows)
    form = card.findChild(QFormLayout)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    for control in (output, browse):
        control.setMinimumWidth(0)
        control.setMaximumWidth(16777215)
        control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return card


class MeasurementView:
    def install_plot(self):
        self.figure = Figure(layout="constrained")
        self.map_axes, self.spectrum_axes = self.figure.subplots(1, 2)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.plot_toolbar = NavigationToolbar2QT(self.canvas, self)
        self.results.insertWidget(0, self.plot_toolbar)
        self.results.insertWidget(1, self.canvas, 1)
        self.log.setMaximumHeight(100)
        self.details_button = QPushButton("Details")
        self.details_button.setCheckable(True)
        self.details_button.setToolTip("Show acquisition messages and output paths")
        self.details_button.toggled.connect(self.log.setVisible)
        self.left.addWidget(self.details_button)
        self.log.hide()
        self._cube_result = None
        self._live_cube = None
        self._selected_cube_pixel = None
        self.latest_pixel_button = QPushButton("Follow latest spectrum")
        self.latest_pixel_button.hide()
        self.latest_pixel_button.clicked.connect(self.follow_latest_pixel)
        self.results.insertWidget(2, self.latest_pixel_button)
        self.canvas.mpl_connect("button_press_event", self.select_pixel)

    def render_measurement(self, kind, value):
        is_cube = kind in {"cube", "cube-live"}
        self.latest_pixel_button.setVisible(is_cube)
        self._cube_result = None
        if not is_cube:
            self._live_cube = None
            self._selected_cube_pixel = None
        self.figure.clear()
        if is_cube:
            self.map_axes, self.spectrum_axes = self.figure.subplots(1, 2)
            if kind == "cube-live":
                image, _wavelength, _intensity, iy, ix, live = value
                if self._live_cube is not live:
                    self._selected_cube_pixel = None
                self._live_cube = live
                self._cube_x, self._cube_y = live.x_v, live.y_v
                self._latest_cube_pixel = (iy, ix)
            else:
                self._live_cube = None
                self._cube_result = value
                self._cube_x, self._cube_y = value.x_v, value.y_v
                image = np.where(value.completed_mask, np.sum(value.intensity, axis=2), np.nan)
                indices = np.argwhere(value.completed_mask)
                self._latest_cube_pixel = tuple(indices[-1]) if indices.size else None
                if self._selected_cube_pixel is not None and self._spectrum_at(*self._selected_cube_pixel) is None:
                    self._selected_cube_pixel = None
            x0, x1 = self._voltage_extent(self._cube_x)
            y0, y1 = self._voltage_extent(self._cube_y)
            self.map_axes.imshow(image, origin="lower", aspect=MIRROR_Y_PER_X_SCALE,
                                 extent=(x0, x1, y0, y1), interpolation="nearest")
            self.map_axes.set(xlabel="Mirror X voltage (V)", ylabel="Mirror Y voltage (V)",
                              title="Integrated intensity")
            self._pixel_marker, = self.map_axes.plot([], [], "+", color="cyan", markersize=10)
            self._draw_cube_spectrum()
        else:
            self.spectrum_axes = self.map_axes = self.figure.add_subplot(111)
            if kind in {"spectrum", "dark"}:
                self.spectrum_axes.plot(value.wavelength_nm, value.intensity)
                title = "Latest spectrum"
                if kind == "dark":
                    title = f"Closed-shutter dark ({value.settings.n_frames} frames / {value.settings.combine_mode})"
                self.spectrum_axes.set(xlabel="Wavelength (nm)", ylabel="Intensity", title=title)
            else:
                image = np.where(value.completed_mask, value.summed_count_rate_cps, np.nan)
                self.map_axes.imshow(image, origin="lower", aspect="equal")
                self.map_axes.set(xlabel="X pixel", ylabel="Y pixel", title="Latest map")
        self.canvas.draw_idle()

    @staticmethod
    def _voltage_extent(axis):
        if len(axis) == 1 or axis[0] == axis[-1]:
            return axis[0] - 0.0005, axis[0] + 0.0005
        half_step = (axis[1] - axis[0]) / 2
        return axis[0] - half_step, axis[-1] + half_step

    def _spectrum_at(self, y, x):
        if self._live_cube is not None:
            return self._live_cube.get(y, x)
        result = self._cube_result
        if (result is not None and 0 <= y < len(result.y_v) and 0 <= x < len(result.x_v)
                and result.completed_mask[y, x]):
            return result.wavelength_nm, result.intensity[y, x]
        return None

    def _draw_cube_spectrum(self):
        selected = self._selected_cube_pixel or self._latest_cube_pixel
        self.spectrum_axes.clear()
        self.spectrum_axes.set(xlabel="Wavelength (nm)", ylabel="Intensity")
        if selected is None:
            self.spectrum_axes.set_title("No completed pixels")
            return
        y, x = selected
        data = self._spectrum_at(y, x)
        if data is None:
            self.spectrum_axes.set_title("Pixel not yet acquired")
            return
        xv, yv = self._cube_x[x], self._cube_y[y]
        self._pixel_marker.set_data([xv], [yv])
        self.spectrum_axes.plot(*data)
        label = "Selected" if self._selected_cube_pixel is not None else "Latest"
        self.spectrum_axes.set_title(f"{label}: X={xv:.4g} V, Y={yv:.4g} V")

    def show_pixel(self, y, x):
        if self._spectrum_at(y, x) is None:
            return
        self._selected_cube_pixel = (y, x)
        self._draw_cube_spectrum()
        self.canvas.draw_idle()

    def follow_latest_pixel(self):
        if self._live_cube is None and self._cube_result is None:
            return
        self._selected_cube_pixel = None
        self._draw_cube_spectrum()
        self.canvas.draw_idle()

    def select_pixel(self, event):
        if self._live_cube is None and self._cube_result is None:
            return
        if (event.inaxes is not self.map_axes or event.xdata is None or event.ydata is None
                or self.plot_toolbar.mode or event.button != 1):
            return
        y = int(np.argmin(np.abs(self._cube_y - event.ydata)))
        x = int(np.argmin(np.abs(self._cube_x - event.xdata)))
        self.show_pixel(y, x)


class CubePanel(MeasurementView, TaskPanel):
    def __init__(self, workspace, pages):
        super().__init__(workspace, "Hyperspectral mapping")
        self.pages = pages
        base = workspace.plan.map_config
        low, high = base.safe_voltage_min_v, base.safe_voltage_max_v
        self.x_start, self.x_stop = number(base.x_start_v, low, high), number(base.x_stop_v, low, high)
        self.y_start, self.y_stop = number(base.y_start_v, low, high), number(base.y_stop_v, low, high)
        self.x_points, self.y_points = integer(base.x_points), integer(base.y_points)
        self.settle = number(base.settle_time_s, 0, 60)
        add_card(self.controls, "Spatial grid", [("X start (V)", self.x_start), ("X stop (V)", self.x_stop),
            ("X points", self.x_points), ("Y start (V)", self.y_start), ("Y stop (V)", self.y_stop),
            ("Y points", self.y_points), ("Mirror settle (s)", self.settle)])
        self.dark = QComboBox()
        self.dark.addItems(["none", "per_center", "per_frame", "once_per_map", "pre_taken"])
        self.dark.setToolTip("once_per_map: capture one stitched dark for this scan. "
                             "pre_taken: use the captured or loaded dark below.")
        self.dark_record = None
        self._pending_dark = None
        self._dark_only = False
        self._saved_run = None
        self.dark_status = QLabel("No reusable dark selected")
        self.dark_status.setWordWrap(True)
        self.capture_dark_button = QPushButton("Capture dark")
        self.capture_dark_button.clicked.connect(self.capture_dark)
        load_dark = QPushButton("Load dark NPZ")
        load_dark.clicked.connect(self.load_dark)
        save_dark = QPushButton("Save dark NPZ")
        save_dark.clicked.connect(self.save_dark)
        view_dark = QPushButton("View dark")
        view_dark.clicked.connect(self.view_dark)
        add_card(self.controls, "Spectrum", [("Dark mode", self.dark),
            (None, self.dark_status), (None, self.capture_dark_button),
            (None, load_dark), (None, save_dark), (None, view_dark)])
        self.output = QLineEdit(str(Path.home() / "Labtools" / "Hyperspectral"))
        self.browse_button = QPushButton("Browse output")
        self.browse_button.clicked.connect(self.browse)
        self.save_output = QCheckBox("Save results to disk")
        self.save_output.setChecked(True)
        output_card(self.controls, self.output, self.browse_button, self.save_output)
        self.save_output.toggled.connect(self.output.setEnabled)
        self.save_output.toggled.connect(self.browse_button.setEnabled)
        note = QLabel("Independent spatial grid. Detector/range/exposure come from Spectrum. Completed pixels and the latest spectrum update during acquisition.")
        note.setWordWrap(True)
        self.controls.addWidget(note)
        self.controls.addStretch(1)
        self.install_plot()
        self.start_button.clicked.connect(self.start)
        enabled = bool(getattr(workspace, "simulation_only", False) or getattr(workspace, "all_hardware_enabled", False))
        self.start_button.setEnabled(enabled)
        self.capture_dark_button.setEnabled(enabled)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, "Cube output", self.output.text())
        if path:
            self.output.setText(path)

    def snapshot(self):
        spectrum = self.pages["Spectrum"]._snapshot_settings()
        config = HyperspectralConfig(self.workspace.plan.configuration_id, spectrum,
            self.x_start.value(), self.x_stop.value(), self.x_points.value(),
            self.y_start.value(), self.y_stop.value(), self.y_points.value(),
            self.settle.value(), self.dark.currentText(), spectrum.backend)
        validate_cube(self.workspace, config, self.selected_dark(config))
        return config

    def selected_dark(self, config):
        return self.dark_record if config.dark_mode == "pre_taken" else None

    def _accept_dark(self, record, *, select=False):
        self.dark_record = record
        label = "Synthetic dark" if record.settings.backend == "simulation" else "Dark"
        self.dark_status.setText(f"{label}: {record.settings.n_frames} frames / {record.settings.combine_mode}\n{record.captured_at}")
        if select:
            self.dark.setCurrentText("pre_taken")
            self._display_dark(record)

    def capture_dark(self):
        if self.busy or not self.capture_dark_button.isEnabled():
            return
        try:
            settings = self.pages["Spectrum"]._snapshot_settings()
            self._saved_run = (self.last_result, getattr(self, "run_settings", None))
            self._dark_only = True
            def capture():
                with self.batch.borrow("Spectrum"):
                    return capture_cube_dark(self.workspace, settings, self.stop_event)
            self.launch(capture, ("Spectrum",))
            self.status.setText("Capturing closed-shutter dark using Spectrum settings")
        except (ValueError, RuntimeError, OSError) as error:
            self._restore_saved_run()
            self.status.setText(str(error))

    def _restore_saved_run(self):
        if self._saved_run is not None:
            self.last_result, self.run_settings = self._saved_run
            self.save_result_button.setEnabled(self.last_result is not None)
        self._saved_run = None
        self._dark_only = False

    def drain_display(self):
        with self._display_lock:
            record, self._pending_dark = self._pending_dark, None
        if record is not None:
            self._accept_dark(record)
        super().drain_display()

    def _publish_dark(self, record):
        with self._display_lock:
            self._pending_dark = record

    def poll(self):
        super().poll()
        if self._dark_only and not self.busy:
            self._restore_saved_run()

    def load_dark(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load spectrum dark", "", "Dark spectra (*.npz)")
        if path:
            try:
                record = load_dark_record(path)
                record.validate_for(self.pages["Spectrum"]._snapshot_settings())
                self._accept_dark(record, select=True)
                self.status.setText("Loaded reusable dark")
            except (ValueError, TypeError, RuntimeError, OSError, BadZipFile) as error:
                self.status.setText(str(error))

    def save_dark(self):
        if self.dark_record is None:
            self.status.setText("Capture or load a dark first")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save spectrum dark", "dark.npz", "Dark spectra (*.npz)")
        if path:
            try:
                target = Path(path).with_suffix(".npz")
                save_dark_record(target, self.dark_record)
                self.status.setText(f"Saved dark: {target}")
            except (ValueError, OSError) as error:
                self.status.setText(str(error))

    def view_dark(self):
        if self.dark_record is None or self.busy:
            return
        self._display_dark(self.dark_record)

    def _display_dark(self, record):
        self.render_measurement("dark", record)
        previous = self._saved_run[0] if self._dark_only and self._saved_run is not None else self.last_result
        if previous is not None and not isinstance(previous, DarkRecord):
            self.latest_pixel_button.setText("Return to map")
            self.latest_pixel_button.show()

    def follow_latest_pixel(self):
        if self._cube_result is None and self._live_cube is None and self.last_result is not None:
            self.latest_pixel_button.setText("Follow latest spectrum")
            self.render_measurement("cube", self.last_result)
        else:
            super().follow_latest_pixel()

    def start(self):
        if self.busy:
            return
        try:
            config = self.snapshot()
            dark = self.selected_dark(config)
            self.latest_pixel_button.setText("Follow latest spectrum")
            save = self.save_output.isChecked()
            if save and not self.output.text().strip():
                raise ValueError("Choose a cube output folder or disable saving")
            self.run_settings = config
            def run():
                with self.batch.borrow("Spectrum"), self.batch.borrow("Intensity map"):
                    path = unique_directory(self.output_path, "cube") / "cube.npz" if save else None
                    return run_cube(self.workspace, config, stop=self.stop_event, output_path=path,
                        display=self.publish, dark=dark, on_dark=self._publish_dark,
                        progress=lambda p: self.report("Capturing one dark for the map" if p.phase == "capturing_dark"
                            else f"Cube: {p.completed_points}/{p.total_points} pixels"))
            self.output_path = Path(self.output.text())
            self.launch(run, ("Spectrum", "Intensity map"))
        except (ValueError, RuntimeError, OSError) as error:
            self.status.setText(str(error))

    def completed(self, result):
        if isinstance(result, DarkRecord):
            self._accept_dark(result, select=True)
            self.status.setText("Dark captured. Save dark NPZ to keep a copy.")
            return
        self.status.setText(f"Cube {result.status}: {result.completed_points} pixels")
        self.log.appendPlainText(str(result.output_path))
        self.displayed_measurement = ("cube", result)
        self.render_measurement("cube", result)


class SequencePanel(MeasurementView, TaskPanel):
    def __init__(self, workspace, pages, program_panel, cube_panel):
        super().__init__(workspace, "Anneal and measure sequences")
        self.pages, self.program_panel, self.cube_panel = pages, program_panel, cube_panel
        self.measurement = QComboBox()
        self.measurement.addItems(["Spectrum", "Intensity map", "Hyperspectral"])
        self.cycles = integer(1)
        source = workspace.plan.hardware_settings
        low = max(workspace.plan.map_config.safe_voltage_min_v, source["minimum_mirror_voltage_v"])
        high = min(workspace.plan.map_config.safe_voltage_max_v, source["maximum_mirror_voltage_v"])
        self.spectrum_x = number(source["home_x_voltage_v"], low, high, 4)
        self.spectrum_y = number(source["home_y_voltage_v"], low, high, 4)
        self.spectrum_settle = number(workspace.plan.map_config.settle_time_s, 0, 60)
        self.spectrum_position_card = add_card(self.controls, "Spectrum position", [("X (V)", self.spectrum_x),
            ("Y (V)", self.spectrum_y), ("Mirror settle (s)", self.spectrum_settle)])
        self.measurement.currentTextChanged.connect(lambda name: self.spectrum_position_card.setVisible(name == "Spectrum"))
        add_card(self.controls, "Repeat plan", [("Measurement", self.measurement), ("Cycles", self.cycles)])
        self.controls.removeWidget(self.spectrum_position_card)
        self.controls.insertWidget(1, self.spectrum_position_card)
        self.save_output = QCheckBox("Save results to disk")
        self.save_output.setChecked(True)
        self.output = QLineEdit(str(Path.home() / "Labtools" / "Sequences"))
        self.browse_button = QPushButton("Browse output")
        self.browse_button.clicked.connect(self.browse)
        output_card(self.controls, self.output, self.browse_button, self.save_output)
        self.save_output.toggled.connect(self.output.setEnabled)
        self.save_output.toggled.connect(self.browse_button.setEnabled)
        note = QLabel("Baseline measurement first, then one anneal and one measurement per cycle. C cycles produce C anneals and C+1 measurements. Settings are snapshotted at Start. Saving off creates no run-output files; the latest result remains displayed. No automatic laser ON.")
        note.setWordWrap(True)
        self.controls.addWidget(note)
        self.controls.addStretch(1)
        self.install_plot()
        self.start_button.clicked.connect(self.start)
        self.start_button.setEnabled(program_panel.start_button.isEnabled() and cube_panel.start_button.isEnabled())

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, "Sequence output", self.output.text())
        if path:
            self.output.setText(path)

    def start(self):
        try:
            program = self.program_panel.snapshot()
            measurement = self.measurement.currentText()
            request = self.cube_panel.snapshot() if measurement == "Hyperspectral" else self.pages["Spectrum"]._snapshot_settings() if measurement == "Spectrum" else self.pages["Intensity map"]._config()
            cube_dark = self.cube_panel.selected_dark(request) if measurement == "Hyperspectral" else None
            cycles, save = self.cycles.value(), self.save_output.isChecked()
            position = (self.spectrum_x.value(), self.spectrum_y.value(), self.spectrum_settle.value()) if measurement == "Spectrum" else None
            self.run_settings = {"program": program, "measurement": measurement, "request": request, "cycles": cycles, "spectrum_position": position}
            output = Path(self.output.text()) if self.output.text().strip() else None
            self.launch(lambda: run_sequence(self.workspace, program, measurement, request, cycles=cycles,
                output_root=output, save_output=save, stop=self.stop_event, report=self.report, display=self.publish, spectrum_position=position, cube_dark=cube_dark))
        except (ValueError, RuntimeError, OSError) as error:
            self.status.setText(str(error))


def combine_annealing(window, program):
    """One visible page, one shared geometry/dwell, one Start/Stop action pair."""
    anneal = window.pages["Annealing"]
    program.hide()
    program.setParent(anneal)
    # Insert mode-specific controls into the existing scrollable Annealing form.
    from PyQt6.QtWidgets import QScrollArea

    scroll = anneal.centralWidget().findChild(QScrollArea)
    form = scroll.widget().layout()
    card = program.controls.itemAt(0).widget()
    form.insertWidget(0, card)
    card.show()
    old = program.first_dwell
    old_form = next(f for f in card.findChildren(QFormLayout) if f.indexOf(old) >= 0)
    old_form.removeRow(old)
    program.first_dwell = anneal.dwell
    form.insertWidget(1, program.preview_button)
    form.insertWidget(2, program.log)
    program.log.setMaximumHeight(130)
    program.preview_button.setCheckable(True)
    program.preview_button.toggled.connect(program.log.setVisible)
    program.preview_button.show()
    program.log.hide()
    program.mode.setCurrentText("Uniform array")
    def mode_changed(mode):
        program.last_dwell.setEnabled(mode == "Dwell ramp array")
        program.spacing.setEnabled(mode == "Dwell ramp array")
        for control in (anneal.x_stop, anneal.y_stop, anneal.x_points, anneal.y_points):
            control.setEnabled(mode != "Single point")
    program.mode.currentTextChanged.connect(mode_changed)
    mode_changed(program.mode.currentText())
    for label in anneal.findChildren(QLabel):
        if label.text() == "Point dwell":
            label.setText("Point / first dwell")
    note = QLabel("Single point uses X start / Y start. Array modes use the shared grid. Dwell ramps follow scan order. Preview doses before Start.")
    note.setWordWrap(True)
    form.insertWidget(1, note)
    original_start = anneal._start
    anneal.start_button.clicked.disconnect()
    anneal.start_button.clicked.connect(lambda: original_start() if program.mode.currentText() == "Uniform array" else program.start())
    anneal.stop_button.clicked.connect(program.request_stop)
    def reflect():
        if program.busy:
            anneal.start_button.setEnabled(False)
            anneal.stop_button.setEnabled(True)
            anneal.status.setText(program.status.text())
        elif getattr(anneal, "_thread", None) is None:
            anneal._update_start_state()
    program.timer.timeout.connect(reflect)


def install_experiment_tabs(window, workspace):
    program = AnnealProgramPanel(workspace, window.pages["Annealing"])
    cube = CubePanel(workspace, window.pages)
    sequence = SequencePanel(workspace, window.pages, program, cube)
    window.pages["Anneal programs"] = program  # internal lifecycle alias, never a tab
    combine_annealing(window, program)
    for name, page in (("Hyperspectral", cube), ("Sequences", sequence)):
        window.pages[name] = page
        window.tabs.insertTab(window.tabs.indexOf(window.laser_panel), page, name)
    restore_experiment_preferences(window, workspace.drafts.display)
    from labtools.gui.retained_run_controls import install_retained_controls

    install_retained_controls(window)


def experiment_preferences(window):
    if "Sequences" not in window.pages:
        return {}
    program, cube, sequence = (window.pages[name] for name in ("Anneal programs", "Hyperspectral", "Sequences"))
    return {"program_mode": program.mode.currentText(), "program_first_s": program.first_dwell.value(),
            "program_last_s": program.last_dwell.value(), "program_spacing": program.spacing.currentText(),
            "cube_x_start": cube.x_start.value(), "cube_x_stop": cube.x_stop.value(),
            "cube_y_start": cube.y_start.value(), "cube_y_stop": cube.y_stop.value(),
            "cube_x_points": cube.x_points.value(), "cube_y_points": cube.y_points.value(), "cube_settle": cube.settle.value(),
            "cube_dark": cube.dark.currentText(), "cube_output": cube.output.text(), "cube_save_output": cube.save_output.isChecked(),
            "sequence_measurement": sequence.measurement.currentText(), "sequence_cycles": sequence.cycles.value(),
            "sequence_save_output": sequence.save_output.isChecked(), "sequence_spectrum_x": sequence.spectrum_x.value(),
            "sequence_spectrum_y": sequence.spectrum_y.value(), "sequence_spectrum_settle": sequence.spectrum_settle.value(),
            "sequence_output": sequence.output.text()}


def restore_experiment_preferences(window, data):
    if "Sequences" not in window.pages:
        return
    program, cube, sequence = (window.pages[name] for name in ("Anneal programs", "Hyperspectral", "Sequences"))
    for key, widget in (("program_mode", program.mode), ("program_spacing", program.spacing),
                        ("cube_dark", cube.dark), ("sequence_measurement", sequence.measurement)):
        if key in data:
            widget.setCurrentText(data[key])
    for key, widget in (("program_first_s", program.first_dwell), ("program_last_s", program.last_dwell),
                        ("sequence_cycles", sequence.cycles), ("sequence_spectrum_x", sequence.spectrum_x),
                        ("sequence_spectrum_y", sequence.spectrum_y), ("sequence_spectrum_settle", sequence.spectrum_settle), ("cube_x_start", cube.x_start), ("cube_x_stop", cube.x_stop),
                        ("cube_y_start", cube.y_start), ("cube_y_stop", cube.y_stop),
                        ("cube_x_points", cube.x_points), ("cube_y_points", cube.y_points), ("cube_settle", cube.settle)):
        if key in data:
            widget.setValue(data[key])
    if "cube_save_output" in data:
        cube.save_output.setChecked(data["cube_save_output"])
    if "sequence_save_output" in data:
        sequence.save_output.setChecked(data["sequence_save_output"])
    for key, widget in (("cube_output", cube.output), ("sequence_output", sequence.output)):
        if key in data:
            widget.setText(data[key])

