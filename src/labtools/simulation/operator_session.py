"""Explicit synthetic mode of the source-backed unified operator workspace.

Reuses read-only native composition for source/limits/ownership only. Native gates
remain unconditional. Existing map/spectrum simulators run on their normal workers.
"""

import hashlib
from dataclasses import asdict, replace
from pathlib import Path

from labtools.runtime.native_workspace import NativeWorkspace
from labtools.runtime.workspace_preferences import WorkspacePreferences
from labtools.simulation.anneal import SimulatedAnneal
from labtools.simulation.workspace_services import InjectedSimulationServices


class SimulationInputs:
    def __init__(self, original, *, realtime):
        self.original = original
        self.realtime = realtime

    def map_config(self, config=None):
        if config is None:
            config = replace(self.original.plan.map_config, backend="simulation", simulation_realtime=self.realtime)
        if config.backend != "simulation":
            raise ValueError("Simulation workspace refuses real map settings")
        self.original.map_config(replace(config, backend="real"))
        return config

    def spectrum_settings(self, settings=None):
        if settings is None:
            settings = replace(self.original.plan.spectrum_request.settings, backend="simulation")
        if settings.backend != "simulation":
            raise ValueError("Simulation workspace refuses real spectrum settings")
        self.original.spectrum_settings(replace(settings, backend="real"))
        return settings

    def preview(self, mapping=None, spectrum=None):
        mapping, spectrum = self.map_config(mapping), self.spectrum_settings(spectrum)
        data = asdict(mapping)
        data["output_root"] = str(data["output_root"])
        return {"draft_only": True, "backend": "simulation", "synthetic": True,
                "execution_enabled": False, "native_execution_enabled": False,
                "simulation_execution_enabled": True, "hardware_opened": False,
                "map": data, "spectrum": asdict(spectrum),
                "model_note": "Existing toy counter/map and range spectrum; not a physical detector model"}


class SimulatedOperatorSession(NativeWorkspace):
    simulation_only = True

    def __init__(self, manifest, *, output_root=None, preferences_path=None, anneal_profile=None, realtime=False):
        if type(realtime) is not bool:
            raise ValueError("Simulation realtime must be boolean")
        root = Path(output_root).expanduser().resolve() if output_root is not None else Path.home() / "Labtools Simulation"
        if preferences_path is None:
            key = hashlib.sha256(str(Path(manifest).expanduser().resolve()).encode()).hexdigest()
            preferences_path = WorkspacePreferences("simulation-operator-" + key, "source-bound").path
        had_preferences = Path(preferences_path).exists()
        super().__init__(manifest, preferences_path=preferences_path, anneal_profile=anneal_profile)
        self.workflows = SimulationInputs(self.workflows, realtime=realtime)
        self.drafts.values["map"] = replace(self.drafts.values["map"], backend="simulation", simulation_realtime=realtime)
        self.drafts.values["spectrum"] = replace(self.drafts.values["spectrum"], backend="simulation")
        if (not had_preferences or output_root is not None
                or self.drafts.values["map"].output_root == self.plan.map_config.output_root):
            self.drafts.values["map"] = replace(self.drafts.values["map"], output_root=root / "Maps")
        if (not had_preferences or output_root is not None
                or self.drafts.values["anneal"].output_root == self.drafts.anneal_base.output_root):
            self.drafts.values["anneal"] = replace(self.drafts.values["anneal"], output_root=root / "Annealing")
        if output_root is not None:
            self.drafts.display["spectrum_output"] = str(root / "Spectra")
        else:
            self.drafts.display.setdefault("spectrum_output", str(root / "Spectra"))
        self.simulated_services = InjectedSimulationServices()
        self.simulated_services.bind(self._ownership)
        self.spectrum_service = self.simulated_services.spectrum
        self.anneal_simulator = SimulatedAnneal(self.simulated_services._require_owner, realtime=realtime)
        self.realtime = realtime

    def describe(self):
        report = super().describe()
        report.update({"workspace_kind": "explicit-simulation", "backend": "simulation", "synthetic": True,
                       "execution_enabled": False, "native_execution_enabled": False,
                       "simulation_execution_enabled": True, "hardware_opened": False,
                       "environment_probed": False, "simulation_realtime": self.realtime,
                       "configured_map": self.workflows.preview(self.drafts.values["map"], self.drafts.values["spectrum"])["map"],
                       "configured_spectrum": asdict(self.drafts.values["spectrum"]),
                       "simulation_models": ["existing toy mirror/gate/counter map", "existing toy range spectrum",
                                             "synthetic anneal grid/shutter/stage", "existing synthetic camera"],
                       "selection": {"policy": "simulation only; no native imports, discovery or real fallback",
                                     "source_profile": "read-only limits/options, not simulated physical identities"},
                       "camera_preview": {"source": "simulation only", "auto_connect": False, "hardware_opened": False},
                       "anneal": {"backend": "simulation", "synthetic": True,
                                  "native_execution_enabled": False, "simulation_execution_enabled": True,
                                  "profile_error": self.drafts.profile_error,
                                  "model": "grid/state/logs only; no heating, dose, physical shutter or stage model"},
                       "simulated_anneal_state": self.anneal_simulator.snapshot()})
        return report

    def acquire_map(self, config=None, **kwargs):
        self._require_open()
        return self.simulated_services.acquire_map(self.workflows.map_config(config), **kwargs)

    async def acquire_spectrum(self, settings=None, **kwargs):
        self._require_open()
        return await self.spectrum_service.acquire(self.workflows.spectrum_settings(settings), **kwargs)

    async def capture_dark(self, settings=None, **kwargs):
        self._require_open()
        return await self.spectrum_service.capture_dark(self.workflows.spectrum_settings(settings), **kwargs)

    def acquire_anneal(self, config=None, **kwargs):
        self._require_open()
        config = self.drafts.validate("anneal", self.drafts.values["anneal"] if config is None else config)
        return self.anneal_simulator.run(config, **kwargs)

    def reserve_camera(self):
        raise RuntimeError("Simulation workspace never reserves or opens a physical camera")
