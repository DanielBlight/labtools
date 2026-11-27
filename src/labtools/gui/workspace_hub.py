"""Configuration/status hub. Workflow settings are not hardware profiles."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from labtools.gui.alignment_gui_horiba import HoribaAlignmentWindow
from labtools.gui.native_anneal_panel import CHECKS, NUMERIC
from labtools.gui.workspace_studio import card, scroll_content
from labtools.runtime.workspace_settings import (
    pack,
    read_settings,
    unpack,
)


def alignment_draft(window):
    panel = window.pages.get("Alignment")
    return HoribaAlignmentWindow._snapshot_settings(panel) if panel is not None else None


def apply_alignment(panel, settings):
    panel.preset_combo.setCurrentText(settings.preset)
    panel._update_preset()
    panel.centre_box.setValue(settings.centre_nm)
    panel.exposure_box.setValue(settings.exposure_s)
    panel.gain_combo.setCurrentIndex(panel.gain_combo.findData(settings.gain))
    panel.speed_combo.setCurrentIndex(panel.speed_combo.findData(settings.speed))
    panel.dark_checkbox.setChecked(settings.subtract_dark)


class WorkspaceHub(QWidget):
    def __init__(self, window, workspace):
        super().__init__()
        self.window = window
        self.workspace = workspace
        self._diagnostic = None
        self._diagnostic_lease = None
        self._executor = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 0)
        title = QLabel("Workspace")
        title.setObjectName("studioTitle")
        layout.addWidget(title)
        scroll, content = scroll_content()
        layout.addWidget(scroll, 1)
        summary, form = card("Configuration and operating mode")
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.configuration = QLabel(workspace.plan.configuration_id)
        self.manifest = QLabel(str(workspace.manifest))
        self.manifest.setWordWrap(True)
        self.mode = QLabel("Simulation" if getattr(workspace, "simulation_only", False) else
                           "All real hardware" if getattr(workspace, "all_hardware_enabled", False) else
                           "Real HORIBA only" if getattr(workspace, "hardware_spectrum_enabled", False) else "Native drafts - execution disabled")
        form.addRow("Configuration", self.configuration)
        form.addRow("Source manifest", self.manifest)
        form.addRow("Mode", self.mode)
        self.profile = QLabel(workspace.drafts.local_profile.profile_id if workspace.drafts.local_profile else
                              workspace.drafts.profile_error or "No local Annealing profile selected")
        self.profile.setWordWrap(True)
        form.addRow("Annealing profile", self.profile)
        self.load_configuration_button = QPushButton("Load configuration…")
        self.load_configuration_button.clicked.connect(self.choose_configuration)
        form.addRow(self.load_configuration_button)
        content.addWidget(summary)
        settings, settings_form = card("Workflow settings")
        note = QLabel("Edit acquisition parameters in the workflow tabs. Load/save settings here without editing hardware profiles or approved limits. Configuration changes require idle devices and a disconnected laser.")
        note.setWordWrap(True)
        settings_form.addRow(note)
        row = QWidget()
        buttons = QGridLayout(row)
        buttons.setContentsMargins(0, 0, 0, 0)
        self.load_settings_button = QPushButton("Load settings…")
        self.export_settings_button = QPushButton("Save settings as…")
        self.save_preferences_button = QPushButton("Save as startup settings")
        self.validate_button = QPushButton("Validate settings")
        for index, button in enumerate((self.load_settings_button, self.export_settings_button, self.save_preferences_button, self.validate_button)):
            buttons.addWidget(button, index // 2, index % 2)
        settings_form.addRow(row)
        self.load_settings_button.clicked.connect(self.choose_settings)
        self.export_settings_button.clicked.connect(self.choose_export)
        self.save_preferences_button.clicked.connect(self.save_startup)
        self.validate_button.clicked.connect(self.validate_current)
        content.addWidget(settings)
        devices, device_form = card("Device and workflow status")
        self.device_table = QTableWidget(0, 2)
        self.device_table.setHorizontalHeaderLabels(["Device / workflow", "Reported status (not a live probe)"])
        self.device_table.horizontalHeader().setStretchLastSection(True)
        self.device_table.setMinimumHeight(245)
        self.device_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        device_form.addRow(self.device_table)
        self.device_note = QLabel("Status refresh does not probe hardware. Most devices connect for one operation, then disconnect. Last-operation status is not a live physical readback.")
        self.device_note.setWordWrap(True)
        device_form.addRow(self.device_note)
        actions = QWidget()
        action_row = QGridLayout(actions)
        action_row.setContentsMargins(0, 0, 0, 0)
        self.refresh_button = QPushButton("Refresh status")
        self.camera_button = QPushButton("Open camera")
        self.spectrum_button = QPushButton("Test spectrum connection")
        self.laser_button = QPushButton("Connect laser controller")
        self.map_button = QPushButton("Test map connections")
        self._device_actions = (self.refresh_button, self.camera_button, self.spectrum_button, self.laser_button, self.map_button)
        self._device_action_layout = action_row
        self._device_columns = None
        self._arrange_device_actions(2)
        device_form.addRow(actions)
        self.refresh_button.clicked.connect(self.refresh)
        self.camera_button.clicked.connect(window.open_camera)
        self.spectrum_button.clicked.connect(window.pages["Spectrum"].test_spectrometer_connection)
        self.laser_button.clicked.connect(lambda: window.laser_panel.command("connect"))
        self.map_button.clicked.connect(self.test_map)
        content.addWidget(devices)
        # Preserve the existing diagnostic widget and status object used by tests.
        self.message = window.overview_status
        self.message.setWordWrap(True)
        content.addWidget(self.message)
        content.addWidget(window.details_toggle)
        content.addWidget(window.report)
        content.addStretch(1)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    @property
    def busy(self):
        return self._diagnostic is not None

    def require_idle(self, *, switching=False):
        laser = getattr(self.workspace, "laser", None)
        if self.window.any_busy() or (switching and laser is not None and laser.connected):
            raise RuntimeError("Stop active workflows and disconnect the laser before changing configuration/settings")
        if switching:
            states = self.workspace._ownership.status().resources
            if any(state.owner is not None for state in states):
                raise RuntimeError("A workspace resource is still reserved")

    def snapshot(self):
        drafts = {"map": self.window.pages["Intensity map"]._config(),
                  "spectrum": self.window.pages["Spectrum"]._snapshot_settings(),
                  "anneal": self.window.pages["Annealing"]._build_config()}
        return pack(self.workspace, drafts, self.window.display_preferences(), alignment_draft(self.window))

    def validate_current(self):
        try:
            self.snapshot()
            self.message.setText("Workflow settings valid. No hardware connected or operation started.")
        except (ValueError, RuntimeError, OSError, TypeError, KeyError) as error:
            self.message.setText("Settings invalid: " + str(error))

    def save_startup(self):
        try:
            self.require_idle()
            self.snapshot()
            self.window.save_preferences()
        except (ValueError, RuntimeError, OSError, TypeError) as error:
            self.message.setText(str(error))

    def _arrange_device_actions(self, columns):
        if columns == self._device_columns:
            return
        self._device_columns = columns
        for index, button in enumerate(self._device_actions):
            self._device_action_layout.addWidget(button, index // columns, index % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange_device_actions(3 if event.size().width() >= 900 else 2 if event.size().width() >= 560 else 1)

    def export_settings(self, path):
        self.require_idle()
        data = self.snapshot()
        # Reuse the existing atomic preference writer's safe replace pattern.
        from labtools.runtime.workspace_preferences import WorkspacePreferences

        path = Path(path)
        store = WorkspacePreferences(self.workspace.plan.configuration_id, self.workspace.drafts.store.fingerprint, path)
        # A settings export has a distinct schema; write atomically, not as startup preferences.
        import os
        import tempfile

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(json.dumps(data, indent=2, allow_nan=False) + "\n")
            os.replace(temporary, store.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.message.setText("Workflow settings exported: " + str(path))

    def _apply(self, data):
        mapping, spectrum, anneal = (self.window.pages[name] for name in ("Intensity map", "Spectrum", "Annealing"))
        mapping._apply_config(data["map"])
        settings = data["spectrum"]
        spectrum.preset_combo.setCurrentText(settings.preset)
        spectrum._update_preset_controls()
        for name, value in (("start_wl", settings.start_nm), ("end_wl", settings.end_nm),
                            ("exposure_box", settings.exposure_s), ("slit_width_box", settings.slit_width_mm),
                            ("overlap_box", settings.overlap_pixels), ("frames_box", settings.n_frames)):
            getattr(spectrum, name).setValue(value)
        spectrum.gain_combo.setCurrentIndex(spectrum.gain_combo.findData(settings.gain))
        spectrum.speed_combo.setCurrentIndex(spectrum.speed_combo.findData(settings.speed))
        spectrum.mode_combo.setCurrentText(settings.combine_mode)
        spectrum.frames_box.setValue(settings.n_frames)
        for field, name in NUMERIC.items():
            getattr(anneal, name).setValue(getattr(data["anneal"], field))
        for field, name in CHECKS.items():
            getattr(anneal, name).setChecked(getattr(data["anneal"], field))
        anneal.output_root.setText(str(data["anneal"].output_root))
        self.workspace.drafts.display = data["display"]
        self.window.restore_display()
        if "alignment" in data and "Alignment" in self.window.pages:
            apply_alignment(self.window.pages["Alignment"], data["alignment"])

    def load_settings(self, path):
        self.require_idle()
        # Validate everything before changing any widget. Restore on apply failure.
        incoming = unpack(self.workspace, read_settings(path))
        previous = unpack(self.workspace, self.snapshot())
        try:
            self._apply(incoming)
        except BaseException:
            self._apply(previous)
            raise
        self.message.setText("Workflow settings loaded. Review tabs; save startup settings if desired.")

    def choose_settings(self):
        try:
            self.require_idle()
            path, _ = QFileDialog.getOpenFileName(self, "Load workflow settings", "", "JSON (*.json)")
            if path:
                self.load_settings(path)
        except (ValueError, RuntimeError, OSError, TypeError, KeyError) as error:
            self.message.setText("Settings not loaded: " + str(error))

    def choose_export(self):
        try:
            self.require_idle()
            path, _ = QFileDialog.getSaveFileName(self, "Save workflow settings", "workflow-settings.json", "JSON (*.json)")
            if path:
                self.export_settings(path)
        except (ValueError, RuntimeError, OSError, TypeError) as error:
            self.message.setText("Settings not saved: " + str(error))

    def choose_configuration(self):
        try:
            self.require_idle(switching=True)
            path, _ = QFileDialog.getOpenFileName(self, "Load source-backed candidate configuration", str(self.workspace.manifest.parent), "JSON (*.json)")
            if path:
                self.switch_configuration(path)
        except (ValueError, RuntimeError, OSError, TypeError) as error:
            self.message.setText("Configuration not changed: " + str(error))

    def switch_configuration(self, path):
        self.require_idle(switching=True)
        from labtools.gui.native_workspace import create_window

        profile = next((stamp.path for stamp in self.workspace.plan.sources if stamp.field == "local_anneal_profile"), None)
        kwargs = {"anneal_profile": profile}
        if getattr(self.workspace, "simulation_only", False):
            kwargs["realtime"] = self.workspace.realtime
        replacement = type(self.workspace)(path, **kwargs)
        try:
            new_window = create_window(replacement)
        except BaseException:
            replacement.close()
            raise
        app = QApplication.instance()
        previous_quit = app.quitOnLastWindowClosed()
        app.setQuitOnLastWindowClosed(False)
        try:
            if not self.window.close():
                new_window.close()
                return False
            self.window._replacement_window = new_window
            app.aboutToQuit.connect(replacement.close)
            new_window.show()
            return True
        finally:
            app.setQuitOnLastWindowClosed(previous_quit)

    def test_map(self):
        if not getattr(self.workspace, "all_hardware_enabled", False) or self._diagnostic is not None:
            return
        try:
            self.require_idle()
            self._diagnostic_lease = self.workspace._ownership.reserve("Intensity map")
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="labtools-map-diagnostic")
            self._diagnostic = self._executor.submit(self.workspace.test_map_connections)
            self.message.setText("Testing LabJack / IDQ connections; SPAD gate will be closed, no scan")
        except (ValueError, RuntimeError, OSError) as error:
            if self._diagnostic_lease is not None:
                self._diagnostic_lease.release()
                self._diagnostic_lease = None
            self.message.setText(str(error))

    def refresh(self):
        if self._diagnostic is not None and self._diagnostic.done():
            try:
                self.message.setText(str(self._diagnostic.result()))
            except Exception as error:  # noqa: BLE001 - display worker failure and release lease
                self.message.setText("Connection test failed: " + str(error))
            finally:
                self._diagnostic = None
                self._diagnostic_lease.release()
                self._diagnostic_lease = None
        runtime = getattr(self.workspace, "_operator_spectrum", None)
        rows = [("HORIBA Spectrum / Alignment", runtime.worker.status().state if runtime else "Execution disabled")]
        rows += list(getattr(self.workspace, "_device_status", {}).items())
        if getattr(self.workspace, "_hardware_fault", None):
            rows.insert(0, ("Hardware session", "Faulted; application teardown required: " + self.workspace._hardware_fault))
        rows += [("Laser", self.window.laser_panel.model.status), ("Camera", self.window.camera_window.status.text())]
        if not getattr(self.workspace, "all_hardware_enabled", False):
            rows += [("Map / Annealing", "Simulation" if getattr(self.workspace, "simulation_only", False) else "Execution disabled")]
        self.device_table.setRowCount(len(rows))
        for row, (name, status) in enumerate(rows):
            self.device_table.setItem(row, 0, QTableWidgetItem(name))
            self.device_table.setItem(row, 1, QTableWidgetItem(status))
        self.device_table.resizeColumnToContents(0)
        idle = not self.window.any_busy()
        laser = getattr(self.workspace, "laser", None)
        self.load_configuration_button.setEnabled(idle and not (laser is not None and laser.connected))
        self.load_settings_button.setEnabled(idle)
        self.export_settings_button.setEnabled(idle)
        self.save_preferences_button.setEnabled(idle)
        self.map_button.setEnabled(idle and getattr(self.workspace, "all_hardware_enabled", False))
        self.spectrum_button.setEnabled(idle and runtime is not None and runtime.worker.status().state not in {"faulted", "closed"})
        self.laser_button.setEnabled(idle and (getattr(self.workspace, "simulation_only", False) or laser is not None) and not self.window.laser_panel.model.connected)

    def shutdown(self):
        self.timer.stop()
        if self._executor is not None:
            self._executor.shutdown(wait=True)


def install_hub(window, workspace):
    old = window.tabs.widget(0)
    window.tabs.removeTab(0)
    window.workspace_hub = WorkspaceHub(window, workspace)
    window.tabs.insertTab(0, window.workspace_hub, "Workspace")
    old.setParent(window)
    old.hide()
    window.tabs.setCurrentIndex(0)
