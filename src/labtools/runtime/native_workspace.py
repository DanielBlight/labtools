"""Native workspace launch composition with a non-configurable execution gate.

Opening this workspace never imports a device module, discovers devices or probes
SDKs. Existing boundaries retain operation-scoped worker/async-loop ownership.
"""

from __future__ import annotations

import importlib
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

from labtools.acquisition.spectrum_service import SpectrumService
from labtools.config.native_candidate import DISABLED_REASON, preflight_candidate
from labtools.runtime.map_devices import MapTransportFactories
from labtools.runtime.native_candidate import (
    DisabledNativeCandidate,
    NativeExecutionDisabled,
)
from labtools.runtime.native_workflows import NativeWorkflowInputs
from labtools.simulation.ownership import WorkspaceOwnership


def _refuse_execution():
    raise NativeExecutionDisabled(DISABLED_REASON)


def _construct(module, name, *args, **kwargs):
    # Deliberately no enable flag, environment override or manifest factory names.
    # The gate precedes imports as well as construction. Removing it requires a
    # separately authorized implementation, not an operator acknowledgement.
    _refuse_execution()
    return getattr(importlib.import_module(module), name)(*args, **kwargs)


def _labjack():
    return _construct("labtools.devices.labjack_u6", "LabJackU6")


def _counter(address):
    return _construct("labtools.devices.idq_time_controller", "IDQTimeController", address)


def _mirror(labjack, *, dio_pin):
    return _construct("labtools.devices.scanning_mirror", "ScanningMirror", labjack, dio_pin=dio_pin)


def _gate(labjack, *, pin):
    return _construct("labtools.devices.spad_gate", "SPADGate", labjack, pin=pin)


def _spectrometer(*args, **kwargs):
    return _construct("labtools.devices.horiba_spectrometer", "HoribaSpectrometer", *args, **kwargs)


class NativeWorkspaceInputError(ValueError):
    """A source-backed candidate could not be composed."""

    def __init__(self, report):
        self.report = report
        super().__init__("; ".join(f"{item['field']}: {item['message']}" for item in report["input_errors"]))


class NativeWorkspace:
    """One existing reservation authority, no persistent native handles.

    This is a native launch route, not a simulation launcher. Public workflow
    requests and even direct calls to its native constructors refuse execution.
    """

    def __init__(self, manifest, *, preferences_path=None, anneal_profile=None):
        self.manifest = Path(manifest).expanduser().resolve()
        report = preflight_candidate(self.manifest)
        if report.errors:
            raise NativeWorkspaceInputError(report.to_data())
        if report.plan.hardware_settings is None:
            data = report.to_data()
            data["inputs_complete"] = False
            data["input_errors"] = [{"field": "source_profile", "message": "Native launch requires a schema-2 source-backed candidate"}]
            raise NativeWorkspaceInputError(data)
        config = report.plan.reservation_config
        shared = tuple(dict.fromkeys((config.map_resources[0], *sorted(set(config.map_resources).intersection(config.spectrum_resources)))))
        extras = tuple(config.configuration_id + ":" + name for name in ("anneal-shutter", "rotation-stage", "anneal-camera"))
        if set(extras) & set(config.resources):
            raise ValueError("Anneal logical resource labels collide with existing resources")
        config = replace(config, resources=config.resources + extras, anneal_resources=shared + extras[:2], camera_resources=(extras[2],))
        config.validate()
        self.plan = replace(report.plan, reservation_config=config)
        self._preflight = replace(report, plan=self.plan)
        self.workflows = NativeWorkflowInputs(self.plan)
        self.spectrum_service = SpectrumService(self._workflow_backend)
        from labtools.runtime.unified_inputs import UnifiedDrafts

        self.drafts = UnifiedDrafts(self, preferences_path, anneal_profile)
        self._preflight = replace(self._preflight, plan=self.plan)
        self._closed = False
        self._ownership = WorkspaceOwnership(self.plan.reservation_config)
        try:
            self.services = DisabledNativeCandidate(
                plan=self.plan, ownership=self._ownership,
                map_factories=MapTransportFactories(_labjack, _counter, _mirror, _gate),
                spectrometer_factory=_spectrometer,
            )
        except BaseException:
            self._ownership.close()
            raise

    def _require_open(self):
        if self._closed:
            raise RuntimeError("Native workspace is closed")
        self.plan.verify_sources()

    def describe(self):
        self._require_open()
        settings = deepcopy(self.plan.hardware_settings)
        preset = self.plan.spectrum_request.settings.preset
        camera_reserved = any(state.owner == "Camera preview" for state in self._ownership.status().resources)
        mapping = asdict(self.plan.map_config)
        mapping["output_root"] = str(mapping["output_root"])
        return {
            **self._preflight.to_data(),
            "configured_map": mapping,
            "configured_spectrum": asdict(self.plan.spectrum_request.settings),
            "workspace_kind": "native-candidate",
            "operator_workflows_bound": True,
            "workflows": ["Intensity map", "Spectrum", "Annealing"],
            "hardware_opened": None if camera_reserved else False,
            "environment_probed": None if camera_reserved else False,
            "experiment_hardware_opened": False,
            "camera_preview": {"explicit_start_available": True, "auto_connect": False,
                               "reservation_active": camera_reserved,
                               "connection_state": "inspect camera window; reservation is not a device readback",
                               "selection": "first available UC480; identity read only after Start",
                               "resources": list(self.plan.reservation_config.camera_resources),
                               "experiment_execution_enabled": False},
            "anneal": {"configuration_origin": "existing anneal defaults plus shared source wiring/envelope",
                       "local_profile": self.drafts.local_profile.profile_id if self.drafts.local_profile else None,
                       "profile_error": self.drafts.profile_error,
                       "sc10_port": self.drafts.anneal_base.sc10_port,
                       "physical_shutter_stage_camera": "not probed by anneal; camera identity/state is shown in separate preview; not interchangeable with spectroscopy TTL shutter",
                       "execution_enabled": False},
            "preferences": {"path": str(self.drafts.store.path), "messages": list(self.drafts.store.messages)},
            "operator_drafts": "validated per-user preferences; source files and standalone QSettings unchanged",
            "selection": {
                "labjack": {"policy": settings["labjack_selection"], "physical_serial": None,
                            "status": "implicit-first-device; not discovered or confirmed"},
                "counter": {"address": settings["counter_address"], "port": settings["counter_port"],
                            "status": "configured endpoint; not contacted"},
                "spectrometer": {"preset": preset, **settings["detectors"][preset],
                                 "status": "source expectations; not device readbacks"},
                "monochromator": {"policy": settings["monochromator_selection"], "physical_identity": None,
                                  "status": "implicit-first-device; not discovered or confirmed"},
                "optical_path": {"resources": sorted(set(self.plan.reservation_config.map_resources)
                                                      & set(self.plan.reservation_config.spectrum_resources)),
                                 "status": "logical exclusion only; physical shutter not verified"},
            },
            "execution_gate": "code-level refusal before native import; no runtime enable route",
            "operation_ownership": "existing map worker / spectrum coroutine; no handles on reservation executor",
        }

    def workflow_preview(self, mapping=None, spectrum=None):
        self._require_open()
        return self.workflows.preview(mapping, spectrum)

    def acquire_map(self, config=None, **kwargs):
        self._require_open()
        config = self.workflows.map_config(config)
        return self.services.acquire_map(config, **kwargs)

    def _workflow_backend(self, settings):
        self._require_open()
        settings = self.workflows.spectrum_settings(settings)
        # Existing candidate refuses here, before constructing a backend/handle.
        return self.services._disabled_backend(settings)

    async def acquire_spectrum(self, settings=None, **kwargs):
        self._require_open()
        settings = self.workflows.spectrum_settings(settings)
        return await self.spectrum_service.acquire(settings, **kwargs)

    async def capture_dark(self, settings=None, **kwargs):
        self._require_open()
        settings = self.workflows.spectrum_settings(settings)
        return await self.spectrum_service.capture_dark(settings, **kwargs)

    def reserve_camera(self):
        self._require_open()
        return self._ownership.reserve("Camera preview")

    def acquire_anneal(self, config=None, **kwargs):
        self._require_open()
        self.drafts.validate("anneal", self.drafts.values["anneal"] if config is None else config)
        _refuse_execution()

    def save_preferences(self, **drafts):
        self._require_open()
        self.drafts.save(**drafts)

    def close(self):
        if not self._closed:
            runtime = getattr(self, "_operator_spectrum", None)
            if runtime is not None:
                runtime.close()
            self._ownership.close()
            self._closed = True

    def __enter__(self):
        try:
            self._require_open()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *args):
        self.close()
