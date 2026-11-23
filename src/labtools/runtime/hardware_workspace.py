"""Explicit all-hardware workspace; opening it never activates outputs."""

from dataclasses import replace

from labtools.runtime.hardware_laser import HardwareLaser
from labtools.runtime.hardware_spectrum_workspace import HardwareSpectrumWorkspace
from labtools.runtime.map_devices import MapTransportFactories
from labtools.runtime.workspace_map_transport import WorkspaceMapTransport


def real_map_factories(source):
    if source["counter_port"] != 5555 or source["labjack_selection"] != "u6.U6()":
        raise ValueError("Source counter port/LabJack selection differs from the deployed map adapter")
    if source["gate_active_high"] is not True:
        raise ValueError("The deployed SPADGate supports active-high wiring only")
    def labjack():
        from labtools.devices.labjack_u6 import LabJackU6

        return LabJackU6()

    def counter(address):
        from labtools.devices.idq_time_controller import IDQTimeController

        return IDQTimeController(address)

    def mirror(device, *, dio_pin):
        from labtools.devices.scanning_mirror import ScanningMirror

        return ScanningMirror(device, dio_pin=dio_pin)

    def gate(device, *, pin):
        from labtools.devices.spad_gate import SPADGate

        if source["gate_active_high"] is not True:
            raise ValueError("The deployed SPADGate supports active-high wiring only")
        return SPADGate(device, pin=pin)

    return MapTransportFactories(labjack, counter, mirror, gate)


class HardwareWorkspace(HardwareSpectrumWorkspace):
    all_hardware_enabled = True

    def __init__(self, manifest, *, preferences_path=None, anneal_profile=None,
                 spectrometer_factory=None, stitcher=None, map_factories=None, laser_factory=None,
                 anneal_acquisition=None, auxiliary_action=None):
        super().__init__(manifest, preferences_path=preferences_path, anneal_profile=anneal_profile,
                         spectrometer_factory=spectrometer_factory, stitcher=stitcher)
        self._hardware_fault = None
        try:
            self._device_status = {name: "Not probed; connects on explicit operation" for name in
                                   ("LabJack / mirrors / SPAD gate", "IDQ counter", "SC10 shutter", "Rotation stage")}
            self._anneal_acquisition = anneal_acquisition
            self._auxiliary_action = auxiliary_action
            self._map_transport = WorkspaceMapTransport(
                ownership=self._ownership, configuration_id=self.plan.configuration_id,
                factories=map_factories or real_map_factories(self.plan.hardware_settings),
            )
            self.laser = HardwareLaser(self, factory=laser_factory)
        except BaseException:
            super().close()
            raise

    def hardware_ready(self):
        if self._hardware_fault:
            raise RuntimeError("Hardware operation faulted; application teardown is required: " + self._hardware_fault)

    def require_owner(self, owner):
        self._require_open()
        self.hardware_ready()
        states = {item.name: item for item in self._ownership.status().resources}
        if any(states[name].owner != owner for name in self._ownership.config.for_workflow(owner)):
            raise PermissionError(f"{owner} requires its workspace reservation")

    def acquire_map(self, config=None, **kwargs):
        config = self.workflows.map_config(config)
        self.require_owner("Intensity map")
        for name in ("LabJack / mirrors / SPAD gate", "IDQ counter"):
            self._device_status[name] = "Acquiring; operation-scoped connection"
        try:
            result = self._map_transport.acquire(config, **kwargs)
        except BaseException as error:
            self._hardware_fault = f"Map operation/cleanup failed: {error!r}"
            for name in ("LabJack / mirrors / SPAD gate", "IDQ counter"):
                self._device_status[name] = "Operation failed; physical state not confirmed"
            raise
        else:
            for name in ("LabJack / mirrors / SPAD gate", "IDQ counter"):
                self._device_status[name] = "Last operation completed; connection released"
            return result

    def test_map_connections(self):
        self.require_owner("Intensity map")
        config = self.workflows.map_config()
        try:
            with self._map_transport._backend(config) as (_, gate, _):
                gate.close()
        except BaseException as error:
            self._hardware_fault = f"Map operation/cleanup failed: {error!r}"
            for name in ("LabJack / mirrors / SPAD gate", "IDQ counter"):
                self._device_status[name] = "Connection test failed; physical state not confirmed"
            raise
        for name in ("LabJack / mirrors / SPAD gate", "IDQ counter"):
            self._device_status[name] = "Connection test completed; released; no scan/count acceptance"
        return "Map connections tested; SPAD gate closed; no scan or count-input acceptance claimed"

    def anneal_config(self, config=None):
        self._require_open()
        if self.drafts.local_profile is None or self.drafts.profile_error:
            raise ValueError("A valid existing local Annealing instrument profile is required; select --anneal-profile or install the reviewed profile")
        config = self.drafts.values["anneal"] if config is None else config
        config = self.drafts.validate("anneal", config)
        # The existing acquisition resolver uses this profile's identity/hash.
        from labtools.config.anneal_workspace import build_config, recipe_from_config

        return build_config(recipe_from_config(config), self.effective_anneal_profile())

    def effective_anneal_profile(self):
        local = self.drafts.local_profile
        base = self.drafts.anneal_base
        return replace(local, minimum_mirror_voltage_v=base.minimum_mirror_voltage_v,
                       maximum_mirror_voltage_v=base.maximum_mirror_voltage_v,
                       maximum_open_time_s=min(local.maximum_open_time_s, base.maximum_open_time_s))

    def acquire_anneal(self, config=None, **kwargs):
        self.require_owner("Annealing")
        config = self.anneal_config(config)
        for name in ("LabJack / mirrors / SPAD gate", "SC10 shutter", "Rotation stage"):
            self._device_status[name] = "Annealing; operation-scoped connection"
        try:
            if self._anneal_acquisition is None:
                from labtools.acquisition.laser_anneal import run_laser_anneal

                result = run_laser_anneal(config, instrument_profile=self.effective_anneal_profile(), **kwargs)
            else:
                result = self._anneal_acquisition(config, **kwargs)
        except BaseException as error:
            self._hardware_fault = f"Annealing operation/cleanup failed: {error!r}"
            for name in ("LabJack / mirrors / SPAD gate", "SC10 shutter", "Rotation stage"):
                self._device_status[name] = "Operation failed; physical state not confirmed"
            raise
        else:
            for name in ("LabJack / mirrors / SPAD gate", "SC10 shutter", "Rotation stage"):
                self._device_status[name] = "Last operation completed; connection released"
            return result

    def auxiliary(self, action, coordinate=None):
        self.require_owner("Annealing")
        self.anneal_config()
        if action not in {"shutter-test", "stage-test", "stage-move"}:
            raise ValueError("Unknown hardware diagnostic")
        if action == "stage-move":
            from labtools.config.anneal_workspace import validate_stage_coordinate

            validate_stage_coordinate(coordinate, self.drafts.local_profile)
        name = "SC10 shutter" if action == "shutter-test" else "Rotation stage"
        self._device_status[name] = "Diagnostic running; operation-scoped connection"
        try:
            result = self._auxiliary_operation(action, coordinate)
        except BaseException as error:
            self._hardware_fault = f"Hardware diagnostic/cleanup failed: {error!r}"
            self._device_status[name] = "Diagnostic failed; physical state not confirmed"
            raise
        self._device_status[name] = "Diagnostic completed; connection released; last result: " + str(result)
        return result

    def _auxiliary_operation(self, action, coordinate=None):
        self.require_owner("Annealing")
        config = self.anneal_config()
        if action not in {"shutter-test", "stage-test", "stage-move"}:
            raise ValueError("Unknown hardware diagnostic")
        if action == "stage-move":
            from labtools.config.anneal_workspace import validate_stage_coordinate

            validate_stage_coordinate(coordinate, self.drafts.local_profile)
        if self._auxiliary_action is not None:
            return self._auxiliary_action(action, config, coordinate)
        if action == "shutter-test":
            from labtools.devices.sc10 import SC10

            with SC10(port=config.sc10_port, baud_rate=config.sc10_baud_rate, timeout_s=config.sc10_timeout_s) as device:
                return str(device.get_state())
        from labtools.devices.kinesis_rotation_stage import KinesisRotationStage

        with KinesisRotationStage(move_timeout_s=config.rotation_stage_timeout_s) as device:
            return str(device.move_to(coordinate) if action == "stage-move" else device.get_position())

    def describe(self):
        report = super().describe()
        report.update({"workspace_kind": "all-hardware", "enabled_workflows": ["Intensity map", "Spectrum", "Alignment", "Annealing", "Laser"],
                       "disabled_workflows": [], "execution_gate": "Explicit --hardware; no automatic output activation",
                       "disabled_reason": None, "device_status": dict(self._device_status),
                       "anneal_ready": self.drafts.local_profile is not None and not self.drafts.profile_error,
                       "laser_status": self.laser.status, "hardware_fault": self._hardware_fault,
                       "hardware_opened": None, "environment_probed": None})
        return report

    def close(self):
        laser = getattr(self, "laser", None)
        if laser is not None:
            laser.close()
        super().close()
