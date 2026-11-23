"""Real map/Annealing bindings using existing acquisition workers and leases."""

from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QTimer

from labtools.gui.intensity_map_gui import IntensityMapWindow
from labtools.gui.laser_anneal_gui import LaserAnnealWindow
from labtools.gui.native_anneal_panel import NativeAnnealPanel
from labtools.gui.native_workflow_panels import NativeMapPanel
from labtools.gui.workspace_panels import OwnedMapPanel


class HardwareMapPanel(NativeMapPanel):
    def __init__(self, *, workspace):
        super().__init__(workspace=workspace)
        self.set_status("Ready - real LabJack / IDQ; connects on Start map")
        self._lock_actions()

    def _lock_actions(self):
        if hasattr(self, "start_button"):
            busy = self.map_controller.busy
            self.start_button.setEnabled(not busy)
            self.resume_button.setEnabled(not busy)
            self.stop_button.setEnabled(busy)
            for button in (self.start_button, self.resume_button, self.stop_button):
                button.setToolTip("")

    start_new = IntensityMapWindow.start_new
    choose_resume = IntensityMapWindow.choose_resume
    _start_worker = OwnedMapPanel._start_worker


class HardwareAnnealPanel(NativeAnnealPanel):
    def __init__(self, *, workspace, camera_window=None):
        self._aux_future = None
        self._aux_lease = None
        self._aux_executor = None
        super().__init__(workspace=workspace, camera_window=camera_window)
        self._aux_timer = QTimer(self)
        self._aux_timer.setInterval(20)
        self._aux_timer.timeout.connect(self._poll_aux)
        self._lock_actions()
        self.status.setText("Ready - real Annealing" if self._profile_ready() else "Install/select a valid reviewed Annealing profile before testing")

    def _profile_ready(self):
        return self.workspace.drafts.local_profile is not None and not self.workspace.drafts.profile_error

    def _lock_actions(self):
        if not hasattr(self, "start_button"):
            return
        idle = self._thread is None and self._aux_future is None
        for name in ("start_button", "test_sc10", "test_stage", "move_to_anneal_stage"):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(idle and self._profile_ready())
                button.setToolTip("" if self._profile_ready() else "Reviewed local Annealing profile required")
        self.stop_button.setEnabled(not idle)

    def _update_start_state(self):
        self._lock_actions()

    def _start(self):
        if self._thread is not None or self._aux_future is not None:
            return
        try:
            config = self._build_config()
            self.workspace.anneal_config(config)
            self._start_worker(config)
        except (ValueError, RuntimeError, OSError) as error:
            self.status.setText(str(error))

    def _aux(self, action, coordinate=None):
        if self._thread is not None or self._aux_future is not None:
            return
        try:
            self.workspace.anneal_config()
            self._aux_lease = self.workspace._ownership.reserve("Annealing")
            if self._aux_executor is None:
                self._aux_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="labtools-anneal-diagnostic")
            self._aux_future = self._aux_executor.submit(self.workspace.auxiliary, action, coordinate)
            self.status.setText("Hardware diagnostic running; waiting for device completion")
            self._aux_timer.start()
        except (ValueError, RuntimeError, OSError) as error:
            if self._aux_lease is not None:
                self._aux_lease.release()
                self._aux_lease = None
            self.status.setText(str(error))
        self._lock_actions()

    def _poll_aux(self):
        if self._aux_future is None or not self._aux_future.done():
            return
        try:
            self.status.setText("Hardware diagnostic: " + str(self._aux_future.result()))
        except Exception as error:  # noqa: BLE001 - display worker failure without losing cleanup
            self.status.setText("Hardware diagnostic failed: " + str(error))
        finally:
            self._aux_future = None
            self._aux_timer.stop()
            self._aux_lease.release()
            self._aux_lease = None
            self._lock_actions()

    def _test_sc10(self):
        self._aux("shutter-test")

    def _test_rotation_stage(self):
        self._aux("stage-test")

    def _move_stage_to_anneal(self):
        self._aux("stage-move", self.anneal_stage_coordinate.value())

    def request_stop(self):
        super().request_stop()
        if self._aux_future is not None:
            self.status.setText("Waiting for the current hardware diagnostic; native calls are not interrupted")

    def _cleanup_worker(self):
        try:
            LaserAnnealWindow._cleanup_worker(self)
        finally:
            self._release_lease()
            self._lock_actions()

    def closeEvent(self, event):
        if self._aux_future is not None:
            event.ignore()
            return
        super().closeEvent(event)
        if event.isAccepted() and self._aux_executor is not None:
            self._aux_executor.shutdown(wait=True)
