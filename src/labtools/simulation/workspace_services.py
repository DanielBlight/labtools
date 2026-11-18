"""Resource-specific simulation services for the existing workspace injection boundary.

Wrap existing simulators; no new registry, device handles or acquisition executor.
"""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from threading import Lock, get_ident

from labtools.acquisition.intensity_map import acquire_intensity_map
from labtools.acquisition.spectrum_service import SpectrumService
from labtools.runtime.map_devices import open_map_devices
from labtools.simulation.spectrum import open_simulated_range


class InjectedSimulationServices:
    """Reuse service objects, but keep backend handles operation-scoped.

    Bind to the workspace's existing ownership authority before starting operations.
    The event log is diagnostic only: it neither reserves nor grants resource access.
    """

    def __init__(self):
        self._ownership = None
        self._events = deque(maxlen=4096)
        self._lock = Lock()
        self.spectrum = SpectrumService(self._spectrum_backend)

    def bind(self, ownership):
        if self._ownership is not None:
            raise RuntimeError("Services already bound to a workspace")
        ownership.config.validate()
        self._ownership = ownership

    def events(self):
        with self._lock:
            return tuple(dict(event) for event in self._events)

    def _record(self, workflow, resource, action, loop=None):
        event = {
            "workflow": workflow, "resource": resource, "action": action,
            "thread": get_ident(), "loop": id(loop) if loop is not None else None,
        }
        with self._lock:
            self._events.append(event)

    def _require_owner(self, workflow):
        if self._ownership is None:
            raise RuntimeError("Bind injected services to workspace ownership before use")
        required = self._ownership.config.for_workflow(workflow)
        states = {resource.name: resource for resource in self._ownership.status().resources}
        if any(states[name].owner != workflow for name in required):
            raise PermissionError(f"{workflow} requires its existing workspace reservation")

    def acquire_map(self, config, **kwargs):
        if config.backend != "simulation":
            raise ValueError("Injected map service refuses real hardware")
        if "device_provider" in kwargs:
            raise ValueError("Injected map service owns its simulation provider")
        self._require_owner("Intensity map")
        return acquire_intensity_map(config, device_provider=self._map_backend, **kwargs)

    @contextmanager
    def _map_backend(self, config):
        self._require_owner("Intensity map")
        services = self
        thread = get_ident()

        class Resource:
            def __init__(self, name, device):
                self.name = name
                self.device = device
                self.closed = False
                services._record("Intensity map", name, "open")

            def __getattr__(self, name):
                attribute = getattr(self.device, name)
                if not callable(attribute):
                    return attribute

                def call(*args, **kwargs):
                    if self.closed or get_ident() != thread:
                        raise RuntimeError("Map resource used outside its operation thread/lifetime")
                    services._require_owner("Intensity map")
                    services._record("Intensity map", self.name, name)
                    return attribute(*args, **kwargs)

                return call

        resources = []
        try:
            with open_map_devices(config) as devices:
                resources = [Resource(name, device) for name, device in zip(
                    ("mirror", "gate", "counter"), devices, strict=True
                )]
                try:
                    yield tuple(resources)
                finally:
                    for resource in resources:
                        resource.closed = True
        finally:
            # Provider teardown has completed before the final diagnostic events.
            for resource in resources:
                self._record("Intensity map", resource.name, "closed")

    @asynccontextmanager
    async def _spectrum_backend(self, settings):
        if settings.backend != "simulation":
            raise ValueError("Injected spectrum service refuses real hardware")
        self._require_owner("Spectrum")
        services = self
        thread = get_ident()
        loop = asyncio.get_running_loop()
        closed = False
        self._record("Spectrum", "detector", "open", loop)
        try:
            async with open_simulated_range(settings) as backend:
                class Detector:
                    def check(self, action):
                        if closed or get_ident() != thread or asyncio.get_running_loop() is not loop:
                            raise RuntimeError("Spectrum resource used outside its operation thread/loop/lifetime")
                        services._require_owner("Spectrum")
                        services._record("Spectrum", "detector", action, loop)

                    async def acquire(self, dark_mode):
                        self.check("acquire")
                        return await backend.acquire(dark_mode)

                    async def capture_dark(self):
                        self.check("capture_dark")
                        return await backend.capture_dark()

                yield Detector()
        finally:
            closed = True
            self._record("Spectrum", "detector", "closed", loop)
