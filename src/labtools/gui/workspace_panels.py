"""Workspace-only adapters; standalone workflow behaviour is unchanged."""

from labtools.gui.intensity_map_gui import IntensityMapWindow
from labtools.gui.spectrum_gui_horiba import HoribaRangeWindow
from labtools.runtime.session import ResourceBusyError


class OwnedMapPanel(IntensityMapWindow):
    def __init__(self, *, ownership, acquisition=None, simulation_only=True):
        self._ownership = ownership
        self._workspace_lease = None
        super().__init__(
            acquisition=acquisition, simulation_only=simulation_only,
            simulation_seed=ownership.config.simulation_seed,
            simulation_realtime=ownership.config.simulation_realtime,
        )
        self.map_controller.idle.connect(self._release_workspace_lease)

    def _release_workspace_lease(self):
        if self._workspace_lease is not None:
            self._workspace_lease.release()
            self._workspace_lease = None

    def _start_worker(self, config):
        if self.map_controller.busy:
            return
        try:
            self._workspace_lease = self._ownership.reserve("Intensity map")
        except ResourceBusyError as error:
            self.set_status(f"Workspace busy: {error}. Wait for cleanup or use Stop all.")
            return
        try:
            super()._start_worker(config)
        finally:
            # Validation refusal/start failure must not strand a reservation.
            if not self.map_controller.busy:
                self._release_workspace_lease()


class OwnedSpectrumPanel(HoribaRangeWindow):
    def __init__(self, *, ownership, service=None, backend="simulation", preset_options=None):
        self._ownership = ownership
        self._workspace_lease = None
        super().__init__(
            service=service, backend=backend,
            configuration_id=ownership.config.configuration_id,
            **({"preset_options": preset_options} if preset_options is not None else {}),
        )

    def _release_workspace_lease(self):
        if self._workspace_lease is not None:
            self._workspace_lease.release()
            self._workspace_lease = None

    def _start_operation(self, factory, done, error, message):
        if self._spectrometer_busy or self._async_tasks:
            return
        try:
            self._workspace_lease = self._ownership.reserve("Spectrum")
        except ResourceBusyError as conflict:
            self.set_status(f"Workspace busy: {conflict}. Wait for cleanup or use Stop all.")
            return
        try:
            super()._start_operation(factory, done, error, message)
        finally:
            if not self._async_tasks:
                self._release_workspace_lease()

    def _thread_finished(self, task):
        try:
            super()._thread_finished(task)
        finally:
            if not self._async_tasks:
                self._release_workspace_lease()
