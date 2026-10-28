"""Opt-in map adapters for an application-owned LabJack session.

Existing standalone windows do not use this module. Counter connections remain
per-map and run on the acquisition thread, not on the LabJack worker.
"""

from contextlib import contextmanager

from labtools.runtime.labjack_service import LabJackWiring


class SessionMirror:
    def __init__(self, lease):
        self._lease = lease

    def move(self, x_voltage, y_voltage):
        self._lease.call("mirror", "move", x_voltage, y_voltage)

    def home(self):
        self._lease.cleanup("mirror", "home")


class SessionCounter:
    """Lease-scoped IDQ count interface; raw services never leave the session."""

    def __init__(self, lease, resource):
        self._lease = lease
        self._resource = resource

    def configure_channel(self, channel, *, threshold_v, edge, enabled=True):
        return self._lease.call(
            self._resource,
            "configure_channel",
            channel,
            threshold_v=threshold_v,
            edge=edge,
            enabled=enabled,
        )

    def get_simultaneous_counts(self, channels, integration_time_s):
        return self._lease.call(
            self._resource,
            "get_simultaneous_counts",
            channels,
            integration_time_s,
        )


class SessionGate:
    def __init__(self, lease):
        self._lease = lease

    def open(self):
        self._lease.call("gate", "open_gate")

    def close(self):
        self._lease.cleanup("gate", "close_gate")


@contextmanager
def real_counter(config):
    from labtools.devices.idq_time_controller import IDQTimeController

    with IDQTimeController(config.time_controller_address) as controller:
        yield controller


class SharedMapProvider:
    """Callable context provider for acquire_intensity_map(device_provider=...).

    Reserve LabJack for the complete acquisition and its home/gate cleanup.
    Backend and fixed wiring must match. No real-to-synthetic fallback exists.
    A simulation counter provider must be explicitly supplied for simulation.
    The caller owns session lifetime; exiting a map releases but does not close it.
    """

    def __init__(
        self,
        session,
        *,
        wiring=None,
        backend="real",
        counter_provider=None,
        counter_resource=None,
        counter_address=None,
        owner="intensity-map",
    ):
        wiring = LabJackWiring() if wiring is None else wiring
        wiring.validate()
        if backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        if backend == "simulation" and counter_provider is None:
            raise ValueError(
                "Simulation requires an explicit synthetic counter provider"
            )
        self.session = session
        self.wiring = wiring
        self.backend = backend
        self.counter_provider = (
            real_counter if counter_provider is None else counter_provider
        )
        if counter_provider is not None and counter_resource is not None:
            raise ValueError("Choose a counter provider or a session counter resource")
        self.counter_resource = counter_resource
        self.counter_address = counter_address
        self.owner = owner

    @contextmanager
    def __call__(self, config):
        config.validate()
        if config.backend != self.backend:
            raise ValueError("Map backend does not match shared provider")
        if self.counter_address is not None:
            from labtools.runtime.idq_count_service import canonical_idq_address

            if (
                canonical_idq_address(config.time_controller_address)
                != self.counter_address
            ):
                raise ValueError("Map IDQ address does not match shared application")
        if (config.mirror_dio_pin, config.spad_gate_pin) != (
            self.wiring.mirror_dio_pin,
            self.wiring.spad_gate_pin,
        ):
            raise ValueError("Map wiring does not match the application-owned LabJack")
        resources = ["mirror", "gate"]
        if self.counter_resource is not None:
            resources.append(self.counter_resource)
        with self.session.reserve(self.owner, resources) as lease:
            if self.counter_resource is not None:
                counter = SessionCounter(lease, self.counter_resource)
                yield SessionMirror(lease), SessionGate(lease), counter
                return
            manager = self.counter_provider(config)
            counter = manager.__enter__()
            try:
                yield SessionMirror(lease), SessionGate(lease), counter
            except BaseException as primary:
                try:
                    manager.__exit__(type(primary), primary, primary.__traceback__)
                except BaseException as cleanup:  # noqa: BLE001 - preserve cancellation/primary failure
                    primary.add_note(f"Counter close also failed: {cleanup!r}")
                raise
            else:
                manager.__exit__(None, None, None)
