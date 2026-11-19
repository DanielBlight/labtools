"""Native workspace launch composition with a non-configurable execution gate.

Opening this workspace never imports a device module, discovers devices or probes
SDKs. Existing boundaries retain operation-scoped worker/async-loop ownership.
"""

from __future__ import annotations

import importlib
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from labtools.config.native_candidate import DISABLED_REASON, preflight_candidate
from labtools.runtime.map_devices import MapTransportFactories
from labtools.runtime.native_candidate import (
    DisabledNativeCandidate,
    NativeExecutionDisabled,
)
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

    def __init__(self, manifest):
        self.manifest = Path(manifest).expanduser().resolve()
        report = preflight_candidate(self.manifest)
        if report.errors:
            raise NativeWorkspaceInputError(report.to_data())
        if report.plan.hardware_settings is None:
            data = report.to_data()
            data["inputs_complete"] = False
            data["input_errors"] = [{"field": "source_profile", "message": "Native launch requires a schema-2 source-backed candidate"}]
            raise NativeWorkspaceInputError(data)
        self._preflight = report
        self.plan = report.plan
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
        mapping = asdict(self.plan.map_config)
        mapping["output_root"] = str(mapping["output_root"])
        return {
            **self._preflight.to_data(),
            "configured_map": mapping,
            "configured_spectrum": asdict(self.plan.spectrum_request.settings),
            "workspace_kind": "native-candidate",
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

    def acquire_map(self, *args, **kwargs):
        self._require_open()
        return self.services.acquire_map(*args, **kwargs)

    async def acquire_spectrum(self):
        self._require_open()
        return await self.services.spectrum.acquire(self.plan.spectrum_request.settings)

    async def capture_dark(self):
        self._require_open()
        return await self.services.spectrum.capture_dark(self.plan.spectrum_request.settings)

    def close(self):
        if not self._closed:
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
