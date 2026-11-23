"""Explicit real HORIBA route; map, Annealing and laser execution remain gated."""

from labtools.runtime.native_workspace import NativeWorkspace
from labtools.runtime.operator_spectrum import ensure_operator_spectrum
from labtools.runtime.workspace_spectrum_transport import WorkspaceSpectrumTransport


class HardwareSpectrumWorkspace(NativeWorkspace):
    hardware_spectrum_enabled = True

    def __init__(self, manifest, *, preferences_path=None, anneal_profile=None, spectrometer_factory=None, stitcher=None):
        super().__init__(manifest, preferences_path=preferences_path, anneal_profile=anneal_profile)
        try:
            self.spectrometer_factory = spectrometer_factory or self._source_spectrometer
            self._hardware_transport = WorkspaceSpectrumTransport(
                ownership=self._ownership, spectrometer_factory=self.spectrometer_factory, stitcher=stitcher,
            )
            self.spectrum_service = self._hardware_transport.service
            ensure_operator_spectrum(self)
        except BaseException:
            self.close()
            raise

    def _source_spectrometer(self, *, preset):
        # Called only by the owning spectrum worker after explicit Start/Acquire.
        from labtools.devices.horiba_spectrometer import HoribaSpectrometer

        expected = self.plan.hardware_settings["detectors"][preset]
        actual = HoribaSpectrometer.PRESETS[preset]
        for field in ("ccd_index", "expected_device_type", "expected_chip_width", "expected_chip_height",
                      "expected_serial_number", "roi", "grating", "mirror_position"):
            value = actual[field]
            if field in {"grating", "mirror_position"}:
                value = value.name
            if value != expected[field]:
                raise ValueError(f"Source {preset}.{field} differs from the deployed HORIBA preset; refusing connection")
        if self.plan.hardware_settings["monochromator_selection"] != "first-discovered":
            raise ValueError("Unsupported monochromator selection")
        return HoribaSpectrometer(preset=preset)

    def describe(self):
        report = super().describe()
        state = self._operator_spectrum.worker.status().state
        report.update({
            "workspace_kind": "hardware-spectrum", "execution_enabled": True,
            "enabled_workflows": ["Spectrum", "Alignment"],
            "disabled_workflows": ["Intensity map", "Annealing", "Laser"],
            "disabled_reason": "Map, Annealing and laser remain gated; real camera is selected independently",
            "execution_gate": "Explicit --hardware-spectrum; no connection until operator action",
            "spectrum_worker_state": state,
            "hardware_opened": False if state == "unopened" else None,
            "environment_probed": False if state == "unopened" else None,
            "hardware_state_note": "Launch is lazy; after an operation, worker state is not a physical readback",
        })
        # This is launch/status metadata, not a physical readback or probe.
        return report
