"""Explicit transport-factory boundary for the existing native spectrum adapter.

Development seam only: no default factory, CLI route or real GUI enablement.
Factory injection is trusted Python code, not a hardware security sandbox.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from threading import get_ident

from labtools.acquisition.spectrum_service import SpectrumService
from labtools.runtime.spectrum_backend import open_real_range


class WorkspaceSpectrumTransport:
    """Reuse a service while constructing native-contract handles per operation.

    The caller retains the existing workspace reservation until worker teardown.
    No handle is submitted to InstrumentSession's executor or retained across loops.
    """

    def __init__(self, *, ownership, spectrometer_factory, stitcher=None):
        if not callable(spectrometer_factory):
            raise TypeError("An explicit spectrometer_factory callable is required")
        self._ownership = ownership
        if stitcher is not None and not callable(stitcher):
            raise TypeError("stitcher must be callable when supplied")
        self._factory = spectrometer_factory
        self._stitcher = stitcher
        self.service = SpectrumService(self._backend)

    def _require_reservation(self, settings):
        settings.validate()
        if settings.backend != "real":
            raise ValueError("Transport-contract adapter requires real settings, not simulation")
        if settings.configuration_id != self._ownership.config.configuration_id:
            raise ValueError("Spectrum configuration_id must match the workspace configuration")
        from labtools.runtime.workflow_batch import has_owner

        if not has_owner(self._ownership, 'Spectrum'):
            raise PermissionError("Spectrum requires the existing workspace reservation")

    @asynccontextmanager
    async def _backend(self, settings):
        self._require_reservation(settings)
        thread = get_ident()
        loop = asyncio.get_running_loop()
        active = True
        boundary = self
        # Existing adapter owns connect/configure/disconnect and error preservation.
        async with open_real_range(
            settings, spectrometer_factory=self._factory,
            **({"stitcher": self._stitcher} if self._stitcher is not None else {}),
        ) as backend:
            class Operation:
                def check(self):
                    if not active or get_ident() != thread or asyncio.get_running_loop() is not loop:
                        raise RuntimeError("Spectrum handle used outside its operation thread/loop/lifetime")
                    boundary._require_reservation(settings)

                async def acquire(self, dark_mode):
                    self.check()
                    return await backend.acquire(dark_mode)

                async def acquire_with_dark(self, segments):
                    self.check()
                    return await backend.acquire_with_dark(segments)

                async def capture_dark_segments(self):
                    self.check()
                    return await backend.capture_dark_segments()

                async def capture_dark(self):
                    self.check()
                    return await backend.capture_dark()

            try:
                yield Operation()
            finally:
                active = False
