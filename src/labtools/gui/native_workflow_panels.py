"""Existing operator panels bound to native drafts; all device actions refused."""

from copy import deepcopy
from dataclasses import replace

from PyQt6.QtWidgets import QLabel

from labtools.config.native_candidate import DISABLED_REASON
from labtools.gui.workspace_panels import OwnedMapPanel, OwnedSpectrumPanel


def _label_native_draft(panel):
    for label in panel.findChildren(QLabel):
        if label.objectName() == "pageSubtitle":
            label.setText("Source-backed native draft. Hardware execution disabled; no devices probed.")


class NativeMapPanel(OwnedMapPanel):
    def __init__(self, *, workspace):
        self.workspace = workspace
        super().__init__(ownership=workspace._ownership, acquisition=workspace.acquire_map, simulation_only=False)
        self.setWindowTitle("Native map - execution disabled")
        config = workspace.plan.map_config
        for control in (self.x_start, self.x_stop, self.y_start, self.y_stop):
            control.setRange(config.safe_voltage_min_v, config.safe_voltage_max_v)
        self._apply_config(config)
        self.simulation_mode.setChecked(False)
        self.simulation_mode.setEnabled(False)
        self.address.setReadOnly(True)
        self.laser_group.setEnabled(False)
        self.laser_group.hide()
        self.laser_light.setText("Laser state: NOT PROBED")
        self.laser_light.setStyleSheet("")
        self._lock_actions()
        self.set_status(DISABLED_REASON)
        _label_native_draft(self)

    def _intensity_map_preferences_v1(self):
        # Native source recipe is authoritative at launch; do not read or overwrite
        # standalone real/simulation QSettings with a draft from this gated window.
        return

    def _save_map_preferences(self):
        return

    def _config(self):
        snapshot = super()._config()
        editable = (
            "x_start_v", "x_stop_v", "x_points", "y_start_v", "y_stop_v", "y_points",
            "integration_time_s", "channels", "channel_thresholds_v", "channel_edges",
            "settle_time_s", "serpentine", "output_root", "save_results",
        )
        config = replace(self.workspace.plan.map_config, **{name: getattr(snapshot, name) for name in editable})
        return self.workspace.workflows.map_config(config)

    def _lock_actions(self):
        if hasattr(self, "simulation_mode"):
            self.simulation_mode.setEnabled(False)
        for name in ("start_button", "resume_button", "stop_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(False)
                button.setToolTip(DISABLED_REASON)

    def _cleanup_worker(self):
        super()._cleanup_worker()
        self._lock_actions()

    def _simulation_changed(self, enabled):
        if hasattr(self, "simulation_mode"):
            previous = self.simulation_mode.blockSignals(True)
            self.simulation_mode.setChecked(False)
            self.simulation_mode.blockSignals(previous)

    def _refuse(self, *args, **kwargs):
        self.set_status(DISABLED_REASON)
        self._lock_actions()

    start_new = _refuse
    choose_resume = _refuse
    _start_worker = _refuse
    connect_laser = _refuse
    turn_laser_on = _refuse
    turn_laser_off = _refuse
    set_laser_current = _refuse


class NativeSpectrumPanel(OwnedSpectrumPanel):
    def __init__(self, *, workspace):
        self.workspace = workspace
        super().__init__(
            ownership=workspace._ownership, service=workspace.spectrum_service, backend="real",
            preset_options=deepcopy(workspace.plan.hardware_settings["detectors"]),
        )
        self.setWindowTitle("Native spectrum - execution disabled")
        settings = workspace.plan.spectrum_request.settings
        self.preset_combo.setCurrentText(settings.preset)
        self._update_preset_controls()
        self.start_wl.setValue(settings.start_nm)
        self.end_wl.setValue(settings.end_nm)
        self.exposure_box.setValue(settings.exposure_s)
        self.gain_combo.setCurrentIndex(self.gain_combo.findData(settings.gain))
        self.speed_combo.setCurrentIndex(self.speed_combo.findData(settings.speed))
        self.slit_width_box.setValue(settings.slit_width_mm)
        self.overlap_box.setValue(settings.overlap_pixels)
        self.mode_combo.setCurrentText(settings.combine_mode)
        self.frames_box.setValue(settings.n_frames)
        self.laser_group.setEnabled(False)
        self.laser_group.hide()
        self.laser_light.setText("Laser state: NOT PROBED")
        self.laser_light.setStyleSheet("")
        self._update_spectrometer_buttons()
        self.set_status(DISABLED_REASON)
        _label_native_draft(self)

    def _snapshot_settings(self):
        return self.workspace.workflows.spectrum_settings(super()._snapshot_settings())

    def _update_spectrometer_buttons(self):
        super()._update_spectrometer_buttons()
        for name in ("connect_button", "acquire_button", "capture_dark_button", "stop_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(False)
                button.setToolTip(DISABLED_REASON)

    def _refuse(self, *args, **kwargs):
        self.set_status(DISABLED_REASON)
        self._update_spectrometer_buttons()

    _start_operation = _refuse
    test_spectrometer_connection = _refuse
    acquire_spectrum = _refuse
    capture_reusable_dark = _refuse
    connect_laser = _refuse
    turn_laser_on = _refuse
    turn_laser_off = _refuse
    set_laser_current = _refuse
