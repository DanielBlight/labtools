"""Unified point-dose, hyperspectral and repeat-sequence operator panels."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import replace
from pathlib import Path
from threading import Event, Lock

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

from labtools.config.anneal_program import AnnealProgram
from labtools.config.hyperspectral import HyperspectralConfig
from labtools.gui.workspace_studio import StudioSplit, add_card, scroll_content
from labtools.runtime.experiment_workflows import (
    run_cube,
    run_program,
    run_sequence,
    unique_directory,
    validate_cube,
)
from labtools.runtime.workflow_batch import Batch


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
        self.results.insertWidget(0, NavigationToolbar2QT(self.canvas, self))
        self.results.insertWidget(1, self.canvas, 1)
        self.log.setMaximumHeight(100)
        self.details_button = QPushButton("Details")
        self.details_button.setCheckable(True)
        self.details_button.setToolTip("Show acquisition messages and output paths")
        self.details_button.toggled.connect(self.log.setVisible)
        self.left.addWidget(self.details_button)
        self.log.hide()
        self._cube_result = None
        self.canvas.mpl_connect("button_press_event", self.select_pixel)

    def render_measurement(self, kind, value):
        self.figure.clear()
        if kind == "spectrum":
            self.spectrum_axes = self.figure.add_subplot(111)
            self.map_axes = self.spectrum_axes
        elif kind == "map":
            self.map_axes = self.figure.add_subplot(111)
            self.spectrum_axes = self.map_axes
        else:
            self.map_axes, self.spectrum_axes = self.figure.subplots(1, 2)
        if kind == "spectrum":
            self.spectrum_axes.plot(value.wavelength_nm, value.intensity)
            self.spectrum_axes.set_title("Latest spectrum")
            self.spectrum_axes.set_visible(True)
        else:
            self.map_axes.set_visible(True)
            if kind == "cube-live":
                image, wavelength, intensity, iy, ix = value
                self.spectrum_axes.plot(wavelength, intensity)
                self.spectrum_axes.set_title(f"Latest pixel X={ix}, Y={iy}")
                self._cube_result = None
            elif kind == "cube":
                self._cube_result = value
                image = np.where(value.completed_mask, np.nansum(value.intensity, axis=2), np.nan)
                indices = np.argwhere(value.completed_mask)
                if indices.size:
                    iy, ix = indices[-1]
                    self.spectrum_axes.plot(value.wavelength_nm, value.intensity[iy, ix])
                    self.spectrum_axes.set_title(f"Pixel X={ix}, Y={iy}")
            else:
                image = np.where(value.completed_mask, value.summed_count_rate_cps, np.nan)
                self._cube_result = None
            self.map_axes.imshow(image, origin="lower", aspect="equal" if kind == "map" else "auto")
            self.map_axes.set(xlabel="X pixel", ylabel="Y pixel", title="Latest map / cube")
        if kind != "map":
            self.spectrum_axes.set(xlabel="Wavelength (nm)", ylabel="Intensity")
        self.canvas.draw_idle()

    def show_pixel(self, y, x):
        result = self._cube_result
        if result is None or result.wavelength_nm.size == 0:
            return
        self.spectrum_axes.clear()
        self.spectrum_axes.plot(result.wavelength_nm, result.intensity[y, x])
        self.spectrum_axes.set(xlabel="Wavelength (nm)", ylabel="Intensity", title=f"Pixel X={x}, Y={y}")
        self.canvas.draw_idle()

    def select_pixel(self, event):
        result = self._cube_result
        if event.inaxes is self.map_axes and event.xdata is not None and event.ydata is not None and result is not None:
            y = min(max(round(event.ydata), 0), len(result.y_v)-1)
            x = min(max(round(event.xdata), 0), len(result.x_v)-1)
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
        self.dark.addItems(["none", "per_center", "per_frame"])
        add_card(self.controls, "Spectrum", [("Dark mode", self.dark)])
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
        self.start_button.setEnabled(bool(getattr(workspace, "simulation_only", False) or getattr(workspace, "all_hardware_enabled", False)))

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
        validate_cube(self.workspace, config)
        return config

    def start(self):
        try:
            config = self.snapshot()
            save = self.save_output.isChecked()
            if save and not self.output.text().strip():
                raise ValueError("Choose a cube output folder or disable saving")
            self.run_settings = config
            def run():
                with self.batch.borrow("Spectrum"), self.batch.borrow("Intensity map"):
                    path = unique_directory(self.output_path, "cube") / "cube.npz" if save else None
                    return run_cube(self.workspace, config, stop=self.stop_event, output_path=path,
                        display=self.publish, progress=lambda p: self.report(f"Cube: {p.completed_points}/{p.total_points} pixels"))
            self.output_path = Path(self.output.text())
            self.launch(run, ("Spectrum", "Intensity map"))
        except (ValueError, RuntimeError, OSError) as error:
            self.status.setText(str(error))

    def completed(self, result):
        self.status.setText(f"Cube {result.status}: {result.completed_points} pixels")
        self.log.appendPlainText(str(result.output_path))
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
            cycles, save = self.cycles.value(), self.save_output.isChecked()
            position = (self.spectrum_x.value(), self.spectrum_y.value(), self.spectrum_settle.value()) if measurement == "Spectrum" else None
            self.run_settings = {"program": program, "measurement": measurement, "request": request, "cycles": cycles, "spectrum_position": position}
            output = Path(self.output.text()) if self.output.text().strip() else None
            self.launch(lambda: run_sequence(self.workspace, program, measurement, request, cycles=cycles,
                output_root=output, save_output=save, stop=self.stop_event, report=self.report, display=self.publish, spectrum_position=position))
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

