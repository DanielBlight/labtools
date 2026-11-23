"""One lazy spectrum worker for unified range and alignment operations.

Workspace reservations remain authoritative. No native imports at composition.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.acquisition.spectrum_service import SpectrumService
from labtools.runtime.spectrum_worker import SpectrumWorker


class WorkerSpectrumService:
    """Async bridge for the existing range panel; never move native handles."""

    def __init__(self, runtime):
        self.runtime = runtime

    async def _wait(self, job, cancelled):
        try:
            while not job.done():
                if cancelled is not None and cancelled():
                    job.cancel()
                await asyncio.sleep(0.01)
            return job.result()
        except asyncio.CancelledError as error:
            job.cancel()
            # Keep the caller's workspace lease until the owning worker finishes.
            while not job.done():
                await asyncio.sleep(0.01)
            if self.runtime.worker.status().state == "faulted":
                raise RuntimeError("Spectrum cleanup failed; application teardown is required") from error
            raise

    async def test_connection(self, settings, *, cancel_requested=None):
        if cancel_requested is not None and cancel_requested():
            raise asyncio.CancelledError("Spectrum operation cancelled before submission")
        self.runtime.validate_range(settings)
        return await self._wait(self.runtime.worker.test_connection(settings, owner="Spectrum"), cancel_requested)

    async def capture_dark(self, settings, *, cancel_requested=None):
        if cancel_requested is not None and cancel_requested():
            raise asyncio.CancelledError("Spectrum operation cancelled before submission")
        self.runtime.validate_range(settings)
        return await self._wait(self.runtime.worker.capture_dark(settings, owner="Spectrum"), cancel_requested)

    async def acquire(self, settings, *, dark_mode="none", dark=None, cancel_requested=None):
        if cancel_requested is not None and cancel_requested():
            raise asyncio.CancelledError("Spectrum operation cancelled before submission")
        self.runtime.validate_range(settings)
        job = self.runtime.worker.acquire(settings, owner="Spectrum", dark_mode=dark_mode, dark=dark)
        return await self._wait(job, cancel_requested)


class OperatorSpectrumRuntime:
    """Shared worker plus source/lease checks for one operator workspace."""

    def __init__(self, workspace, range_service):
        self.workspace = workspace
        self.backend = "simulation" if getattr(workspace, "simulation_only", False) else "real"
        self._range_service = range_service
        self.service = SpectrumService(self._range, self._alignment)
        self.worker = SpectrumWorker(self.service, backend=self.backend)
        self.facade = WorkerSpectrumService(self)

    def require_lease(self):
        self.workspace._require_open()
        check = getattr(self.workspace, "hardware_ready", None)
        if check is not None:
            check()
        self.workspace.plan.verify_sources()
        ownership = self.workspace._ownership
        from labtools.runtime.workflow_batch import has_owner

        if not has_owner(ownership, 'Spectrum'):
            raise PermissionError("Spectrum/alignment requires the workspace Spectrum reservation")

    def validate_range(self, settings):
        self.require_lease()
        return self.workspace.workflows.spectrum_settings(settings)

    def validate_alignment(self, settings):
        self.require_lease()
        if not isinstance(settings, AlignmentSettings):
            raise TypeError("AlignmentSettings required")
        if settings.backend != self.backend or settings.configuration_id != self.workspace.plan.configuration_id:
            raise ValueError("Alignment backend/configuration must match the workspace")
        options = self.workspace.plan.hardware_settings["detectors"].get(settings.preset)
        if options is None:
            raise ValueError("Alignment detector is absent from the source profile")
        settings.validate_detector(options)
        return settings

    @asynccontextmanager
    async def _range(self, settings):
        self.validate_range(settings)
        async with self._range_service._backend_factory(settings) as backend:
            yield backend

    @asynccontextmanager
    async def _alignment(self, settings):
        self.validate_alignment(settings)
        if self.backend == "simulation":
            from labtools.simulation.spectrum import open_simulated_alignment

            context = open_simulated_alignment(settings)
        else:
            from labtools.runtime.spectrum_backend import open_real_alignment

            context = open_real_alignment(settings, spectrometer_factory=self.workspace.spectrometer_factory)
        async with context as backend:
            runtime = self

            class CheckedBackend:
                actual_centre_nm = backend.actual_centre_nm

                async def capture(self, subtract_dark):
                    runtime.validate_alignment(settings)
                    return await backend.capture(subtract_dark)

            yield CheckedBackend()

    def close(self):
        self.worker.close()


def ensure_operator_spectrum(workspace):
    runtime = getattr(workspace, "_operator_spectrum", None)
    if runtime is None:
        runtime = OperatorSpectrumRuntime(workspace, workspace.spectrum_service)
        workspace._operator_spectrum = runtime
        workspace.spectrum_service = runtime.facade
    return runtime
