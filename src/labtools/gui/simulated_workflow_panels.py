"""Synthetic bindings of the existing operator panels and worker lifecycles."""

from copy import deepcopy
from dataclasses import replace

from PyQt6.QtWidgets import QLabel

from labtools.gui.native_anneal_panel import NativeAnnealPanel
from labtools.gui.workspace_panels import OwnedMapPanel, OwnedSpectrumPanel
from labtools.runtime.session import ResourceBusyError


def label_simulation(panel):
    for label in panel.findChildren(QLabel):
        if label.objectName() == "pageSubtitle":
            label.setText("Simulation")


class SimulatedMapPanel(OwnedMapPanel):
    def __init__(self, *, workspace):
        self.workspace = workspace
        super().__init__(ownership=workspace._ownership, acquisition=workspace.acquire_map, simulation_only=True)
        config = workspace.drafts.values["map"]
        for control in (self.x_start, self.x_stop, self.y_start, self.y_stop):
            control.setRange(config.safe_voltage_min_v, config.safe_voltage_max_v)
        self._apply_config(config)
        self.simulation_mode.setChecked(True)
        self.simulation_mode.setEnabled(False)
        self.address.setReadOnly(True)
        self.address.setToolTip("Source endpoint retained for provenance only; never contacted in simulation")
        self.laser_group.setEnabled(False)
        self.laser_group.hide()
        self.laser_light.setText("SIMULATED optical path; no physical laser")
        self.laser_light.setStyleSheet("")
        self.set_status("Ready")
        label_simulation(self)

    def _intensity_map_preferences_v1(self):
        return

    def _save_map_preferences(self):
        return

    def _config(self):
        current = super()._config()
        fields = ("x_start_v", "x_stop_v", "x_points", "y_start_v", "y_stop_v", "y_points",
                  "integration_time_s", "channels", "channel_thresholds_v", "channel_edges",
                  "settle_time_s", "serpentine", "output_root", "save_results")
        config = replace(self.workspace.drafts.values["map"], **{name: getattr(current, name) for name in fields})
        return self.workspace.workflows.map_config(config)


class SimulatedSpectrumPanel(OwnedSpectrumPanel):
    def __init__(self, *, workspace):
        self.workspace = workspace
        options = deepcopy(workspace.plan.hardware_settings["detectors"])
        # These are source option tokens for exercising the GUI, not simulated
        # physical readbacks or a claim that the toy backend models detector gain.
        for detector in options.values():
            detector["gains"] = tuple(("Synthetic option: " + label, token) for label, token in detector["gains"])
            detector["speeds"] = tuple(("Synthetic option: " + label, token) for label, token in detector["speeds"])
        super().__init__(ownership=workspace._ownership, service=workspace.spectrum_service,
                         backend="simulation", preset_options=options)
        settings = workspace.drafts.values["spectrum"]
        self.preset_combo.setCurrentText(settings.preset)
        self._update_preset_controls()
        for widget, value in ((self.start_wl, settings.start_nm), (self.end_wl, settings.end_nm),
                              (self.exposure_box, settings.exposure_s), (self.slit_width_box, settings.slit_width_mm),
                              (self.overlap_box, settings.overlap_pixels), (self.frames_box, settings.n_frames)):
            widget.setValue(value)
        self.gain_combo.setCurrentIndex(self.gain_combo.findData(settings.gain))
        self.speed_combo.setCurrentIndex(self.speed_combo.findData(settings.speed))
        self.mode_combo.setCurrentText(settings.combine_mode)
        self.laser_group.setEnabled(False)
        self.laser_group.hide()
        self.laser_light.setText("SIMULATED optical path; no physical laser")
        self.laser_light.setStyleSheet("")
        self.set_status("Ready")
        label_simulation(self)

    def _snapshot_settings(self):
        return self.workspace.workflows.spectrum_settings(super()._snapshot_settings())


class SimulatedAnnealPanel(NativeAnnealPanel):
    def __init__(self, *, workspace, camera_window=None):
        super().__init__(workspace=workspace, camera_window=camera_window)
        self.setWindowTitle("SIMULATED annealing")
        self.confirm.hide()
        self._show_state()
        self.status.setText("Ready")

    def _update_start_state(self):
        if hasattr(self, "start_button"):
            self.start_button.setEnabled(self._thread is None)

    def _lock_actions(self):
        super()._lock_actions()
        self.start_button.setEnabled(self._thread is None)
        self.start_button.setToolTip("Run synthetic anneal; no hardware")
        self.stop_button.setEnabled(self._thread is not None)
        self.stop_button.setToolTip("Stop synthetic anneal and wait for cleanup")

    def _start(self):
        if self._thread is not None:
            return
        try:
            self._start_worker(self._build_config())
        except (ValueError, TypeError, OSError, ResourceBusyError) as error:
            self.status.setText("Synthetic anneal not started: " + str(error))

    def _show_state(self):
        state = self.workspace.anneal_simulator.snapshot()
        self.shutter_state.setText(f"SIMULATED shutter: {state['shutter']} | stage coordinate: {state['stage_coordinate']}")

    def _on_status(self, message):
        self.status.setText(message)
        self._show_state()

    def _on_completed(self, result):
        self._show_state()
        self.status.setText(f"SIMULATED anneal {'stopped' if result.stopped else 'completed'}: "
                            f"{result.completed_points}/{result.total_points} points")

    def _on_failed(self, error):
        self._show_state()
        self.status.setText("SIMULATED anneal failed: " + error)

    def _cleanup_worker(self):
        super()._cleanup_worker()
        self._show_state()
