"""Minimal shared manual-mirror/intensity-map composition; no eager native imports."""

from __future__ import annotations

from functools import partial
from threading import RLock

from labtools.acquisition.intensity_map import acquire_intensity_map
from labtools.runtime.labjack_service import LabJackWiring, open_labjack_service
from labtools.runtime.session import InstrumentSession, ResourceBusyError
from labtools.runtime.shared_map import SharedMapProvider


class ManualMirrorService:
    """A narrow application-owned manual lease; calls run on the session worker."""

    def __init__(self, session, *, owner="manual-mirror"):
        self._session = session
        self._owner = owner
        self._lease = None
        self._lock = RLock()

    @property
    def connected(self):
        with self._lock:
            return self._lease is not None

    def connect(self):
        """Reserve the mirror without connecting hardware or moving it."""
        with self._lock:
            if self._lease is not None:
                raise RuntimeError("Manual mirror is already connected")
            self._lease = self._session.reserve(self._owner, ("mirror",))

    def move(self, x_voltage, y_voltage):
        with self._lock:
            lease = self._lease
        if lease is None:
            raise RuntimeError("Manual mirror is not connected")
        lease.call("mirror", "move", x_voltage, y_voltage)

    def disconnect(self):
        """Release only the manual lease; never home or close application hardware."""
        with self._lock:
            lease, self._lease = self._lease, None
        if lease is not None:
            lease.release()

    def close(self):
        self.disconnect()

    def status(self):
        return self._session.status()


class SharedMirrorMapApplication:
    """Own one session and compose the two migrated tools around it."""

    def __init__(
        self,
        *,
        wiring=None,
        service_factory=None,
        backend="real",
        counter_provider=None,
        time_controller_address="169.254.99.159",
        idq_service_factory=None,
    ):
        if backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        wiring = LabJackWiring() if wiring is None else wiring
        self._simulation_service = None
        counter_resource = None
        counter_address = None
        if backend == "real":
            from labtools.runtime.idq_count_service import (
                IDQCountService,
                canonical_idq_address,
                idq_resource_name,
            )

            counter_address = canonical_idq_address(time_controller_address)
            counter_resource = idq_resource_name(counter_address)
            labjack_factory = service_factory or partial(open_labjack_service, wiring)
            idq_factory = idq_service_factory or partial(
                IDQCountService, counter_address
            )
            self.session = InstrumentSession(
                {"labjack": labjack_factory, counter_resource: idq_factory},
                aliases={"mirror": "labjack", "gate": "labjack"},
                cleanup_methods={"labjack": ("home", "close_gate")},
            )
        else:
            if service_factory is not None or counter_provider is not None:
                raise ValueError(
                    "Shared simulation owns its service and synthetic counter provider"
                )
            from labtools.simulation.map_devices import SimulatedMapState
            from labtools.simulation.shared_map import (
                SharedSimulatedLabJackService,
                synthetic_counter_provider,
            )

            state = SimulatedMapState()
            service = SharedSimulatedLabJackService(state)
            self._simulation_service = service
            self.session = InstrumentSession(
                {"labjack": lambda: service},
                aliases={"mirror": "labjack", "gate": "labjack"},
                cleanup_methods={"labjack": ("home", "close_gate")},
            )
            counter_provider = synthetic_counter_provider(state)
        self.manual_mirror = ManualMirrorService(self.session)
        self.map_provider = SharedMapProvider(
            self.session,
            wiring=wiring,
            backend=backend,
            counter_provider=counter_provider,
            counter_resource=counter_resource,
            counter_address=counter_address,
        )
        self.map_acquisition = partial(
            acquire_intensity_map, device_provider=self.map_provider
        )

    def create_mirror_window(self):
        from labtools.gui.mirror_voltage_gui import MirrorWindow

        return MirrorWindow(manual_service=self.manual_mirror)

    def create_map_window(self):
        from labtools.gui.intensity_map_gui import IntensityMapWindow

        return IntensityMapWindow(
            acquisition=self.map_acquisition,
            shared_mode=True,
        )

    def status(self):
        return self.session.status()

    def simulation_status(self):
        """Return detached synthetic state, or None for the real composition."""
        service = self._simulation_service
        return None if service is None else service.snapshot()

    def close(self):
        if self.manual_mirror.connected:
            raise ResourceBusyError(
                "Close the manual mirror tool before application shutdown"
            )
        if self._simulation_service is not None:
            status = self.session.status().resources[0]
            if not status.connected:
                with self.session.reserve("application-shutdown", ("mirror",)) as lease:
                    lease.call("mirror", "snapshot")
        self.session.close()
