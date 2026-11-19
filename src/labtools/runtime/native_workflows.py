"""Native operator draft validation, independent of Qt and device imports.

Edits are in-memory drafts, not approved limits or changes to source provenance.
"""

from copy import deepcopy
from dataclasses import asdict

from labtools.config.intensity_map import IntensityMapConfig
from labtools.config.spectrum import SpectrumSettings


class NativeWorkflowInputs:
    def __init__(self, plan):
        self.plan = plan

    def map_config(self, config=None):
        self.plan.verify_sources()
        config = self.plan.map_config if config is None else config
        if not isinstance(config, IntensityMapConfig):
            raise TypeError("Map draft must be IntensityMapConfig")
        config.validate()
        if config.backend != "real":
            raise ValueError("Native map draft requires real backend; no simulation fallback")
        for field in ("time_controller_address", "mirror_dio_pin", "spad_gate_pin",
                      "safe_voltage_min_v", "safe_voltage_max_v"):
            if getattr(config, field) != getattr(self.plan.map_config, field):
                raise ValueError(f"Map {field} is bound to the source profile; edit the source and relaunch")
        return config

    def spectrum_settings(self, settings=None):
        self.plan.verify_sources()
        settings = self.plan.spectrum_request.settings if settings is None else settings
        if not isinstance(settings, SpectrumSettings):
            raise TypeError("Spectrum draft must be SpectrumSettings")
        settings.validate()
        if settings.backend != "real" or settings.configuration_id != self.plan.configuration_id:
            raise ValueError("Native spectrum backend/configuration identity is source-bound")
        detector = self.plan.hardware_settings["detectors"].get(settings.preset)
        if detector is None:
            raise ValueError("Detector preset is absent from source profile")
        if (settings.exposure_s < detector["minimum_exposure_s"]
                or settings.gain not in {item[1] for item in detector["gains"]}
                or settings.speed not in {item[1] for item in detector["speeds"]}):
            raise ValueError("Spectrum draft exceeds source detector options/exposure floor")
        return settings

    def preview(self, mapping=None, spectrum=None):
        mapping = self.map_config(mapping)
        spectrum = self.spectrum_settings(spectrum)
        data = asdict(mapping)
        data["output_root"] = str(data["output_root"])
        return {
            "draft_only": True, "execution_enabled": False, "hardware_opened": False,
            "source_files_changed": False,
            "map": data, "spectrum": asdict(spectrum),
            "detector_expectations_not_readbacks": deepcopy(self.plan.hardware_settings["detectors"][spectrum.preset]),
            "map_worker": "existing MapController / MapWorker",
            "spectrum_worker": "existing QThread / AsyncTaskRunner / SpectrumService",
            "limits_note": "Source software envelope; preview is not connected-device acceptance",
        }
