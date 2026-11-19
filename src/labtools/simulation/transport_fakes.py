"""Fixed fake native-contract transports built on the existing synthetic models.

No dynamic factory names, SDK imports, real transports or physical settings approval.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import replace
from threading import Lock, get_ident

import numpy as np

from labtools.runtime.map_devices import MapTransportFactories
from labtools.simulation.map_devices import (
    SimulatedGate,
    SimulatedMapState,
    SimulatedMirror,
    SimulatedTimeController,
)
from labtools.simulation.spectrum import open_simulated_range


class TransportTrace:
    """Bounded diagnostics and one-shot fault injection, never a resource registry."""

    def __init__(self):
        self._lock = Lock()
        self._events = deque(maxlen=4096)
        self._next_id = 0
        self._fault = None

    def allocate(self):
        with self._lock:
            self._next_id += 1
            return self._next_id

    def fail_next(self, resource, action):
        with self._lock:
            self._fault = (resource, action)

    def record(self, handle, resource, action, loop=None):
        with self._lock:
            self._events.append({"handle": handle, "resource": resource, "action": action,
                                 "thread": get_ident(), "loop": id(loop) if loop else None})
            if self._fault == (resource, action):
                self._fault = None
                raise OSError(f"Injected fake {resource} {action} failure")

    def events(self):
        with self._lock:
            return tuple(dict(event) for event in self._events)


class _Handle:
    def __init__(self, trace, resource, loop=None):
        self.trace, self.resource, self.loop = trace, resource, loop
        self.thread = get_ident()
        self.handle = trace.allocate()
        self.closed = False
        self.record("construct")

    def record(self, action):
        if self.closed or get_ident() != self.thread:
            raise RuntimeError("Fake handle thread/lifetime violation")
        if self.loop is not None and asyncio.get_running_loop() is not self.loop:
            raise RuntimeError("Fake handle event-loop violation")
        self.trace.record(self.handle, self.resource, action, self.loop)

    def close(self):
        try:
            self.record("closed")
        finally:
            self.closed = True


def map_factories(config, trace):
    """Each provider operation gets one isolated existing synthetic scene."""
    state = SimulatedMapState()

    class Jack(_Handle):
        def __init__(self):
            super().__init__(trace, "labjack")

        def __enter__(self):
            self.record("enter")
            return self

        def __exit__(self, *args):
            try:
                self.close()
            finally:
                state.closed = True

    class Mirror:
        def __init__(self, jack, *, dio_pin):
            self.handle = _Handle(trace, "mirror")
            self.device = SimulatedMirror(state, config)

        def move(self, x, y):
            self.handle.record("move")
            self.device.move(x, y)

        def home(self):
            self.handle.record("home")
            self.device.home()

    class Gate:
        def __init__(self, jack, *, pin):
            self.handle = _Handle(trace, "gate")
            self.device = SimulatedGate(state)

        def open(self):
            self.handle.record("open")
            self.device.open()

        def close(self):
            self.handle.record("close")
            self.device.close()

    class Counter:
        def __init__(self, address):
            self.handle = _Handle(trace, "counter")
            self.device = SimulatedTimeController(state, config)

        def __enter__(self):
            self.handle.record("enter")
            return self

        def __exit__(self, *args):
            self.handle.close()

        def configure_channel(self, *args, **kwargs):
            self.handle.record("configure")
            self.device.configure_channel(*args, **kwargs)

        def get_simultaneous_counts(self, *args):
            self.handle.record("read")
            return self.device.get_simultaneous_counts(*args)

    return MapTransportFactories(Jack, Counter, Mirror, Gate)


def spectrum_factory(settings, trace):
    """Adapt the existing toy scene to the existing native range contract."""
    class Spectrometer:
        def __init__(self, *, preset):
            self.handle = _Handle(trace, "spectrometer", asyncio.get_running_loop())
            self._context = None
            self._backend = None
            # Range planner uses these two SDK-shaped collaborators only.
            self.ccd = self
            self.mono = self

        def id(self):
            return "fake-mono"

        async def connect(self):
            self.handle.record("connect")
            self._context = open_simulated_range(replace(settings, backend="simulation"))
            self._backend = await self._context.__aenter__()

        async def configure(self, **kwargs):
            self.handle.record("configure")

        async def prepare_wavelength_axis(self):
            self.handle.record("prepare")
            return (settings.start_nm + settings.end_nm) / 2

        async def range_mode_center_wavelengths(self, *args):
            self.handle.record("centres")
            return [(settings.start_nm + settings.end_nm) / 2]

        async def set_wavelength(self, centre):
            self.handle.record("wavelength")
            return centre

        async def get_spectrum(self, **kwargs):
            self.handle.record("acquire")
            mode = kwargs.get("dark_frame_mode", "none")
            return await self._backend.acquire(mode)

        async def get_dark_spectrum(self, **kwargs):
            self.handle.record("dark")
            return await self._backend.capture_dark()

        async def disconnect(self):
            try:
                if self._backend is not None:
                    await self._context.__aexit__(None, None, None)
            finally:
                self.handle.close()

    return Spectrometer


def single_capture_stitch(captures, start, end):
    """Explicit one-centre fake stitcher, not vendor stitching validation."""
    if len(captures) != 1:
        raise ValueError("Fake transport composition supports exactly one spectral centre")
    x = np.asarray(captures[0][0], dtype=float)
    y = np.asarray(captures[0][1][0], dtype=float)
    keep = (x >= start) & (x <= end)
    if not np.any(keep):
        raise ValueError("Fake spectrum does not cover requested range")
    return x[keep], y[keep]
