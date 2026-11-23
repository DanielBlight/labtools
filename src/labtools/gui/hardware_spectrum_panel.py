"""Enable only the existing spectrum controls on the explicit HORIBA route."""

from labtools.gui.native_workflow_panels import NativeSpectrumPanel
from labtools.gui.spectrum_gui_horiba import HoribaRangeWindow
from labtools.gui.workspace_panels import OwnedSpectrumPanel


class HardwareSpectrumPanel(NativeSpectrumPanel):
    def __init__(self, *, workspace):
        super().__init__(workspace=workspace)
        self.setWindowTitle("Spectrum")
        self.set_status("Ready - real HORIBA; no device connected")
        self._update_spectrometer_buttons()

    def _update_spectrometer_buttons(self):
        HoribaRangeWindow._update_spectrometer_buttons(self)
        if self.workspace._operator_spectrum.worker.status().state == "faulted":
            for name in ("connect_button", "acquire_button", "capture_dark_button"):
                button = getattr(self, name, None)
                if button is not None:
                    button.setEnabled(False)

    def _start_operation(self, *args):
        if self.workspace._operator_spectrum.worker.status().state == "faulted":
            self.set_status("Spectrum worker faulted; application teardown is required")
            return
        return OwnedSpectrumPanel._start_operation(self, *args)

    def _thread_finished(self, task):
        super()._thread_finished(task)
        if self.workspace._operator_spectrum.worker.status().state == "faulted":
            self.set_status("Spectrum worker faulted; application teardown is required")
            self._update_spectrometer_buttons()

    test_spectrometer_connection = HoribaRangeWindow.test_spectrometer_connection
    acquire_spectrum = HoribaRangeWindow.acquire_spectrum
    capture_reusable_dark = HoribaRangeWindow.capture_reusable_dark
