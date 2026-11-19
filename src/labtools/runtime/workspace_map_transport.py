"""Reservation-aware map transport boundary; no default factories or GUI enablement."""

from contextlib import contextmanager
from threading import get_ident

from labtools.acquisition.intensity_map import acquire_intensity_map
from labtools.runtime.map_devices import MapTransportFactories, open_map_devices


class WorkspaceMapTransport:
    """Use existing provider/acquisition cleanup on the caller's synchronous worker.

    Factory injection is trusted Python code, not a hardware security sandbox.
    The caller owns lease release after worker teardown. Handles are operation-scoped.
    """

    def __init__(self, *, ownership, configuration_id, factories):
        if not isinstance(factories, MapTransportFactories):
            raise TypeError("Explicit MapTransportFactories required")
        factories.validate()
        if configuration_id != ownership.config.configuration_id:
            raise ValueError("Map configuration identity must match workspace configuration")
        self._ownership = ownership
        self._configuration_id = configuration_id
        self._factories = factories

    def _require_reservation(self, config):
        config.validate()
        if config.backend != "real":
            raise ValueError("Map transport boundary requires real-contract settings")
        if self._configuration_id != self._ownership.config.configuration_id:
            raise ValueError("Workspace configuration identity changed")
        states = {resource.name: resource for resource in self._ownership.status().resources}
        names = self._ownership.config.for_workflow("Intensity map")
        if any(states[name].owner != "Intensity map" for name in names):
            raise PermissionError("Intensity map requires its existing workspace reservation")

    def acquire(self, config, **kwargs):
        self._require_reservation(config)
        if "device_provider" in kwargs:
            raise ValueError("Map transport boundary owns the device provider")
        return acquire_intensity_map(config, device_provider=self._backend, **kwargs)

    @contextmanager
    def _backend(self, config):
        self._require_reservation(config)
        thread = get_ident()
        active = True
        boundary = self

        class Resource:
            def __init__(self, device):
                self._device = device

            def __getattr__(self, name):
                attribute = getattr(self._device, name)
                if not callable(attribute):
                    return attribute

                def call(*args, **kwargs):
                    if not active or get_ident() != thread:
                        raise RuntimeError("Map handle used outside its operation thread/lifetime")
                    boundary._require_reservation(config)
                    return attribute(*args, **kwargs)

                return call

        with open_map_devices(config, factories=self._factories) as devices:
            try:
                yield tuple(Resource(device) for device in devices)
            finally:
                active = False
