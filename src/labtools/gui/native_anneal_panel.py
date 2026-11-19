"""Existing anneal GUI/worker integrated with the unified ownership and gate."""

from dataclasses import replace
from pathlib import Path

from PyQt6.QtWidgets import QPushButton

from labtools.config.native_candidate import DISABLED_REASON
from labtools.gui.laser_anneal_gui import LaserAnnealWindow

NUMERIC = {
    "x_start_v": "x_start", "x_stop_v": "x_stop", "x_points": "x_points",
    "y_start_v": "y_start", "y_stop_v": "y_stop", "y_points": "y_points", "passes": "passes",
    "point_dwell_s": "dwell", "mirror_settle_s": "settle",
    "anneal_rotation_coordinate": "anneal_stage_coordinate",
    "return_rotation_coordinate": "return_stage_coordinate", "maximum_open_time_s": "max_open",
}
CHECKS = {"serpentine": "serpentine", "return_rotation_stage": "return_stage", "save_run_log": "save_log"}


class NativeAnnealPanel(LaserAnnealWindow):
    def __init__(self, *, workspace, camera_window=None):
        self.workspace = workspace
        self._workspace_lease = None
        super().__init__(acquisition=workspace.acquire_anneal, recipe_controls=False, camera_window=camera_window)
        config = workspace.drafts.values["anneal"]
        for control in (self.x_start, self.x_stop, self.y_start, self.y_stop):
            control.setRange(config.minimum_mirror_voltage_v, config.maximum_mirror_voltage_v)
        widgets = [getattr(self, name) for name in (*NUMERIC.values(), *CHECKS.values())]
        blocked = [widget.blockSignals(True) for widget in widgets]
        try:
            for field, name in NUMERIC.items():
                getattr(self, name).setValue(getattr(config, field))
            for field, name in CHECKS.items():
                getattr(self, name).setChecked(getattr(config, field))
        finally:
            for widget, previous in zip(widgets, blocked, strict=True):
                widget.blockSignals(previous)
        self.output_root.setText(str(config.output_root))
        self.sc10_port.setText(config.sc10_port)
        self.sc10_port.setReadOnly(True)
        self.confirm.setChecked(False)
        self.confirm.setEnabled(False)
        self.shutter_state.setText("Shutter: NOT PROBED")
        self.camera_status.setText("Camera: NOT PROBED")
        self.setWindowTitle("Native annealing - execution disabled")
        self._lock_actions()
        self._update_estimate()
        self.status.setText(workspace.drafts.profile_error or DISABLED_REASON)

    def _restore_settings(self):
        return

    def _save_settings(self):
        return

    def _build_config(self):
        config = replace(
            self.workspace.drafts.anneal_base,
            **{field: getattr(self, name).value() for field, name in NUMERIC.items()},
            **{field: getattr(self, name).isChecked() for field, name in CHECKS.items()},
            output_root=Path(self.output_root.text().strip()),
        )
        return self.workspace.drafts.validate("anneal", config)

    def _lock_actions(self):
        # Experiment/manual entry points remain refused. Camera opens separately;
        # its explicit Start controls only the camera, never annealing hardware.
        for button in self.findChildren(QPushButton):
            if self.camera_window.isAncestorOf(button):
                continue
            if button is not self.open_camera_button and button.text().lower() not in {"browse", "browse...", "browse…"}:
                button.setEnabled(False)
                button.setToolTip(DISABLED_REASON)

    def _update_start_state(self):
        if hasattr(self, "start_button"):
            self.start_button.setEnabled(False)

    def _refuse(self, *args, **kwargs):
        self.status.setText(DISABLED_REASON)
        self._lock_actions()

    _start = _refuse
    _test_sc10 = _refuse
    _move_stage_to_anneal = _refuse
    _test_rotation_stage = _refuse

    def _start_worker(self, config):
        # Trusted internal worker seam for the existing runtime gate. Public Start
        # stays refused; even a direct worker invocation cannot open devices.
        if self._thread is not None:
            return
        self.workspace.drafts.validate("anneal", config)
        self._workspace_lease = self.workspace._ownership.reserve("Annealing")
        try:
            super()._start_worker(config)
        except BaseException:
            if self._thread is None or not self._thread.isRunning():
                self._cleanup_worker()
            raise
        self._lock_actions()

    def request_stop(self):
        if self._thread is not None:
            self._stop()
        if self._camera_thread is not None:
            self._stop_camera()

    def _release_lease(self):
        if self._workspace_lease is not None:
            self._workspace_lease.release()
            self._workspace_lease = None

    def _cleanup_worker(self):
        try:
            super()._cleanup_worker()
            self.shutter_state.setText("Shutter: NOT PROBED")
            self._lock_actions()
        finally:
            self._release_lease()

    def _on_failed(self, error):
        # A gate refusal is not evidence that a shutter-close command was issued.
        self.shutter_state.setText("Shutter: NOT PROBED")
        self.status.setText(error)
