"""Labtools-styled stage popup and optional multi-Z intensity-map controls."""

from types import MethodType

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from labtools.gui.workspace_studio import add_card, scroll_content
from labtools.runtime.focus_stack import FocusPlan, run_focus_stack
from labtools.runtime.sample_stage import AXES, SampleStage
from labtools.runtime.workflow_batch import Batch


def number(value, low, high, decimals=3):
    box = QDoubleSpinBox()
    box.setRange(low, high)
    box.setDecimals(decimals)
    box.setValue(value)
    box.setKeyboardTracking(False)
    return box


def integer(value, low, high):
    box = QSpinBox()
    box.setRange(low, high)
    box.setValue(value)
    return box


def row(*widgets):
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    for child in widgets:
        layout.addWidget(child)
    return widget


class StagePopup(QWidget):
    def __init__(self, workspace, parent):
        super().__init__(parent, Qt.WindowType.Window)
        self.workspace = workspace
        self.service = SampleStage(simulated=bool(workspace.simulation_only), realtime=False)
        self.future = None
        self.token = None
        self.lease = None
        self.setWindowTitle("Labtools | Sample stage")
        self.resize(980, 650)
        root = QVBoxLayout(self)
        heading = QLabel("Sample stage")
        heading.setObjectName("studioTitle")
        root.addWidget(heading)
        note = QLabel("X = axis 0  |  Z = axis 1  |  Y = axis 2. DC ramps take about 0.5 s. "
                      "Single step ramps DC to zero first and leaves it at zero. "
                      "Close DAISY before connecting. +/- are controller directions, not objective clearance.")
        note.setWordWrap(True)
        root.addWidget(note)
        self.connect_button = QPushButton("Connect USB" if not self.service.simulated else "Connect simulation")
        self.disconnect_button = QPushButton("Disconnect")
        self.refresh_button = QPushButton("Refresh readback")
        self.stop_button = QPushButton("Stop")
        root.addWidget(row(self.connect_button, self.disconnect_button, self.refresh_button, self.stop_button))
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        operation = QWidget()
        operation_layout = QVBoxLayout(operation)
        scroll, content = scroll_content()
        operation_layout.addWidget(scroll)
        self.grid = QGridLayout()
        content.addLayout(self.grid)
        content.addStretch(1)
        self.cards = []
        self.axes = {}
        for name, axis in AXES:
            position = QLabel("Not connected")
            position.setObjectName("studioTitle")
            state = QLabel("No readback")
            state.setWordWrap(True)
            target = number(0, -10000, 10000)
            absolute = QPushButton("Move abs")
            relative = QPushButton("Move rel")
            minus, plus = QPushButton("Single step -"), QPushButton("Single step +")
            dc = number(0, 0, 60)
            apply_dc = QPushButton("Ramp DC")
            zero = QPushButton("Ramp to zero")
            amplitude = number(30 if axis == 1 else 60, 0, 60, 1)
            frequency = integer(50 if axis == 1 else 200, 1, 2000)
            apply_amplitude = QPushButton("Apply amplitude")
            apply_frequency = QPushButton("Apply frequency")
            enable, disable = QPushButton("Enable output"), QPushButton("Ramp zero / disable")
            card = add_card(content, f"{name} / controller axis {axis + 1}", [
                (None, position), (None, state), ("Target / delta (um)", target),
                (None, row(absolute, relative)), (None, row(minus, plus)),
                ("DC offset (V)", dc), (None, row(apply_dc, zero)),
                ("Step amplitude (V)", amplitude), (None, apply_amplitude),
                ("Step frequency (Hz)", frequency), (None, apply_frequency),
                (None, enable), (None, disable),
            ])
            content.removeWidget(card)
            self.cards.append(card)
            self.axes[axis] = {"position": position, "state": state, "dc": dc,
                               "amplitude": amplitude, "frequency": frequency}
            absolute.clicked.connect(lambda _=False, a=axis, b=target: self.command("absolute", a, b.value() * 1e-6))
            relative.clicked.connect(lambda _=False, a=axis, b=target: self.command("relative", a, b.value() * 1e-6))
            minus.clicked.connect(lambda _=False, a=axis: self.command("step", a, -1))
            plus.clicked.connect(lambda _=False, a=axis: self.command("step", a, 1))
            apply_dc.clicked.connect(lambda _=False, a=axis, b=dc: self.command("ramp", a, b.value()))
            zero.clicked.connect(lambda _=False, a=axis: self.command("ramp", a, 0))
            apply_amplitude.clicked.connect(lambda _=False, a=axis, b=amplitude: self.command("amplitude", a, b.value()))
            apply_frequency.clicked.connect(lambda _=False, a=axis, b=frequency: self.command("frequency", a, b.value()))
            enable.clicked.connect(lambda _=False, a=axis: self.command("enable", a, True))
            disable.clicked.connect(lambda _=False, a=axis: self.command("enable", a, False))
        self.tabs.addTab(operation, "Operation")
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText("Controller settings are read on Connect/Refresh. LUT, trigger, quadrature and "
                                  "sensor configuration are left unchanged. No settings are written on opening this window.")
        self.tabs.addTab(self.details, "Readback / details")
        self.status = QLabel("Disconnected" + (" / SIMULATION" if self.service.simulated else " / USB"))
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.connect_button.clicked.connect(lambda: self.command("connect"))
        self.disconnect_button.clicked.connect(lambda: self.command("disconnect"))
        self.refresh_button.clicked.connect(lambda: self.command("read"))
        self.stop_button.clicked.connect(self.request_stop)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self._arrange()
        self.hide()

    @property
    def busy(self):
        return self.future is not None

    def _arrange(self):
        columns = 3 if self.width() >= 850 else 1
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)

    def resizeEvent(self, event):
        if hasattr(self, "cards"):
            self._arrange()
        super().resizeEvent(event)

    def command(self, command, axis=1, value=None):
        if self.busy:
            return
        try:
            if command not in {"read", "disconnect"}:
                self.workspace._require_open()
            if command not in {"read", "connect", "disconnect"} and not self.service.simulated:
                self.workspace.hardware_ready()
            # Reserve the optical path before any manual sample motion/settings.
            if command not in {"read", "connect", "disconnect"}:
                self.lease = Batch(self.workspace._ownership, ("Intensity map", "Spectrum", "Annealing"))
            self.token = self.service.claim()
            self.future = self.service.submit(self.token, command, axis=axis, value=value)
            self.status.setText("Running " + command)
        except Exception as error:  # noqa: BLE001 - GUI boundary reports driver/worker errors and preserves cleanup
            self._release()
            self.status.setText(str(error))

    def _release(self):
        if self.token is not None:
            self.service.release(self.token)
            self.token = None
        if self.lease is not None:
            self.lease.release()
            self.lease = None

    def poll(self):
        if self.future is not None and self.future.done():
            try:
                result = self.future.result()
                self.reflect(result)
                self.status.setText("Ready / " + ("SIMULATION" if self.service.simulated else "USB") +
                                    (" / connected" if result["connected"] else " / disconnected"))
            except Exception as error:  # noqa: BLE001 - GUI boundary reports driver/worker errors and preserves cleanup
                self.status.setText(f"Stage command failed: {error}")
            finally:
                self.future = None
                self._release()
        reserved = self.service.busy
        for card in self.cards:
            card.setEnabled(self.service.connected and not reserved)
        self.connect_button.setEnabled(not self.service.connected and not reserved)
        self.disconnect_button.setEnabled(self.service.connected and not reserved)
        self.refresh_button.setEnabled(self.service.connected and not reserved)
        self.stop_button.setEnabled(reserved)

    def reflect(self, snapshot):
        import json
        self.details.setPlainText(json.dumps(snapshot, indent=2))
        if not snapshot["connected"]:
            for controls in self.axes.values():
                controls["position"].setText("Disconnected")
            return
        for name, axis in AXES:
            data = snapshot["axes"][name]
            controls = self.axes[axis]
            controls["position"].setText(f"{data['position_m'] * 1e6:.3f} um")
            controls["state"].setText(f"DC {data['dc_v']:.3f} V | Output {'ON' if data['enabled'] else 'OFF'}\n"
                                       f"Limit: {data['limit'] or 'none'} | {', '.join(data['status']) or 'idle'}")
            for widget_name, key in (("dc", "dc_v"), ("amplitude", "amplitude_v"), ("frequency", "frequency_hz")):
                if not controls[widget_name].hasFocus():
                    controls[widget_name].setValue(data[key])

    def request_stop(self):
        self.service.request_stop()
        self.status.setText("Stop requested; holding DC, no automatic return or step")

    def closeEvent(self, event):
        if self.busy:
            self.request_stop()
            event.ignore()
        else:
            self.hide()
            event.accept()

    def shutdown(self):
        self.service.shutdown()
        self.timer.stop()


class FocusControls(QWidget):
    def __init__(self, panel, stage):
        super().__init__()
        self.panel, self.stage = panel, stage
        self.token = None
        self.active_plan = None
        self.run = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.enabled = QCheckBox("Multiple Z focuses")
        self.levels = QLineEdit("0, 10, 20, 30, 40, 50, 60")
        self.levels.setToolTip("Explicit DC voltages in acquisition order, each between 0 and 60 V")
        self.sweeps = integer(1, 1, 50)
        for field in (self.levels, self.sweeps):
            field.setMinimumWidth(0)
            field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.browse = QComboBox()
        self.common_scale = QCheckBox("Common colour scale for retained maps")
        self.common_scale.setChecked(True)
        note = QLabel("If value >1, one 60V step is taken in +Z before repeating the DC sweep.")
        note.setWordWrap(True)
        focus_card = add_card(root, "Z focus stack", [(None, self.enabled), ("DC levels (V)", self.levels),
            ("DC sweeps", self.sweeps), (None, note),
            ("Retained map", self.browse), (None, self.common_scale)])
        focus_form = focus_card.findChild(QFormLayout)
        if focus_form is None:
            raise RuntimeError("Focus-stack form layout was not created")
        focus_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.browse.currentIndexChanged.connect(self.show_map)
        self.common_scale.toggled.connect(lambda: self.show_map(self.browse.currentIndex()))
        self.original_start = panel._start_worker
        self.original_acquisition = panel.map_controller._acquisition
        panel._start_worker = MethodType(lambda _panel, config: self.start(config), panel)
        panel.map_controller._acquisition = self.acquire
        panel.map_controller.idle.connect(self.idle)
        panel.map_controller.progress.connect(self.progress)
        self.restore(panel.workspace.drafts.display)

    def preferences(self):
        return {"focus_enabled": self.enabled.isChecked(), "focus_levels": self.levels.text(),
                "focus_sweeps": self.sweeps.value()}

    def restore(self, data):
        if "focus_levels" in data:
            self.levels.setText(data["focus_levels"])
        if "focus_enabled" in data:
            self.enabled.setChecked(data["focus_enabled"])
        if "focus_sweeps" in data:
            self.sweeps.setValue(data["focus_sweeps"])

    def plan(self):
        values = tuple(float(v.strip()) for v in self.levels.text().replace(";", ",").split(",") if v.strip())
        return FocusPlan(values, self.sweeps.value(), steps_per_extension=1,
                         direction=1, settle_s=0.2).validate()

    def start(self, config):
        if self.panel.map_controller.busy:
            return
        if not self.enabled.isChecked():
            self.active_plan = None
            self.run = None
            self.browse.clear()
            return self.original_start(config)
        try:
            if self.panel._resume_directory is not None:
                raise ValueError("Focus stacks cannot resume a single-map checkpoint; start a new stack")
            plan = self.plan()
            if not self.stage.connected:
                raise RuntimeError("Open Stage and Connect before starting multiple Z focuses")
            self.token = self.stage.claim()
            self.active_plan = plan
            self.run = None
            self.browse.clear()
            self.original_start(config)
        except Exception as error:  # noqa: BLE001 - GUI boundary reports driver/worker errors and preserves cleanup
            self.panel.set_status(str(error))
        finally:
            if not self.panel.map_controller.busy:
                self.release()

    def acquire(self, config, **kwargs):
        if self.active_plan is None:
            return self.original_acquisition(config, **kwargs)
        def retain(run):
            self.run = run
            self.panel.retained_run.set({"settings": config, "result": run})
        try:
            last, _run = run_focus_stack(self.stage, self.token, self.active_plan, config,
                self.original_acquisition, progress_callback=kwargs.get("progress_callback"),
                cancel_requested=kwargs.get("cancel_requested"), retain=retain)
            if last is None:
                from labtools.runtime.focus_stack import empty_map

                last = empty_map(config)
            return last
        finally:
            if self.run is not None:
                retain(self.run)

    def progress(self, _snapshot):
        run = self.run
        if run is not None and run.get("active") is not None:
            entry = run["active"]
            self.panel.plot_meta.setText(
                f"Focus map {len(run['maps']) + 1}/{len(self.active_plan.voltages) * self.active_plan.sweeps} | "
                f"Sweep {entry['sweep'] + 1} | Z DC {entry['requested_dc_v']:g} V"
            )

    def release(self):
        if self.token is not None:
            self.stage.release(self.token)
            self.token = None

    def idle(self):
        self.release()
        if self.run is None:
            return
        self.browse.blockSignals(True)
        self.browse.clear()
        for entry in self.run["maps"]:
            self.browse.addItem(f"Sweep {entry['sweep'] + 1}, DC {entry['requested_dc_v']:g} V")
        self.browse.blockSignals(False)
        if self.browse.count():
            self.browse.setCurrentIndex(self.browse.count() - 1)
            self.show_map(self.browse.currentIndex())
        self.panel.set_status(f"Focus stack {self.run['status']}: {len(self.run['maps'])} maps retained; "
                              "stage holds last offset. Save before a new run or closing.")

    def show_map(self, index):
        if self.panel.map_controller.busy or self.run is None or not 0 <= index < len(self.run["maps"]):
            return
        result = self.run["maps"][index]["result"]
        panel = self.panel
        panel._latest_plot_values = result.summed_count_rate_cps
        panel.image.set_data(np.ma.masked_invalid(result.summed_count_rate_cps))
        panel._set_map_display_geometry(result.x_values_v, result.y_values_v, result.summed_count_rate_cps.shape)
        panel.axes.set_title(self.browse.itemText(index))
        panel._refresh_colour_scale()
        if self.common_scale.isChecked() and not panel.custom_colour_limits.isChecked():
            arrays = [m["result"].summed_count_rate_cps for m in self.run["maps"]]
            lower, upper = [], []
            for array in arrays:
                values = array[np.isfinite(array)]
                if panel.log_colour_scale.isChecked():
                    values = values[values > 0]
                if values.size:
                    lower.append(float(values.min()))
                    upper.append(float(values.max()))
            if lower:
                lo, hi = min(lower), max(upper)
                panel.image.set_clim(lo, hi if hi > lo else lo + max(1, abs(lo) * .01))
        panel.canvas.draw_idle()


def install_sample_stage(window, workspace):
    popup = StagePopup(workspace, window)
    popup.setStyleSheet(window.styleSheet())
    window.stage_window = popup
    window.pages["Stage"] = popup
    window.stage_button = QPushButton("Stage")
    camera = window.camera_button
    window.stage_button.setObjectName("stageAction")
    window.stage_button.setStyleSheet(camera.styleSheet().replace("#cameraAction", "#stageAction"))
    window.stage_button.setFont(camera.font())
    window.stage_button.setCursor(camera.cursor())
    window.stage_button.setFixedSize(camera.size())
    def show():
        popup.show()
        popup.raise_()
        popup.activateWindow()
    window.stage_button.clicked.connect(show)
    for layout in window.findChildren(QHBoxLayout):
        index = layout.indexOf(window.mirror_button)
        if index >= 0:
            layout.insertWidget(index + 1, window.stage_button)
            break
    else:
        raise RuntimeError("Mirror header layout not found")
    panel = window.pages["Intensity map"]
    controls = FocusControls(panel, popup.service)
    panel.focus_controls = controls
    # Keep focus options with the map's scrollable acquisition controls.
    scrolls = panel.findChildren(QScrollArea)
    target = next(scroll.widget().layout() for scroll in scrolls if scroll.widget() and scroll.widget().isAncestorOf(panel.x_start))
    target.insertWidget(1, controls)
