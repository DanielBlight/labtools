"""Source-bound manual mirror commands and positioned spectra, no Qt/native import."""

import asyncio
import math
import time
from contextlib import asynccontextmanager
from threading import Event

from labtools.runtime.workflow_batch import has_owner


def validate_position(workspace, x, y, settle_s=0.0):
    workspace._require_open()
    workspace.plan.verify_sources()
    if getattr(workspace, "all_hardware_enabled", False):
        workspace.hardware_ready()
    if not (getattr(workspace, "simulation_only", False) or getattr(workspace, "all_hardware_enabled", False)):
        raise RuntimeError("Mirror positioning requires --simulate or --hardware")
    source = workspace.plan.hardware_settings
    low = max(workspace.plan.map_config.safe_voltage_min_v, source["minimum_mirror_voltage_v"])
    high = min(workspace.plan.map_config.safe_voltage_max_v, source["maximum_mirror_voltage_v"])
    for value in (x, y):
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"Mirror target must be finite and within source limits {low:g}..{high:g} V")
    if type(settle_s) not in (int, float) or not math.isfinite(settle_s) or not 0 <= settle_s <= 60:
        raise ValueError("Mirror settle must be finite and between 0 and 60 s")
    return float(x), float(y), float(settle_s)


@asynccontextmanager
async def open_workspace_mirror(workspace, *, home_on_exit):
    if not has_owner(workspace._ownership, "Intensity map"):
        raise PermissionError("Mirror operation requires the existing map-resource lease")
    source = workspace.plan.hardware_settings
    if getattr(workspace, "simulation_only", False):
        class SimulatedMirror:
            async def move_to(self, x, y):
                if not has_owner(workspace._ownership, "Intensity map"):
                    raise PermissionError("Mirror lease lost")
                workspace._mirror_last_commanded = (x, y)
            async def home(self):
                await self.move_to(source["home_x_voltage_v"], source["home_y_voltage_v"])
        mirror = SimulatedMirror()
        try:
            yield mirror
        finally:
            if home_on_exit:
                await mirror.home()
        return
    factories = workspace._map_transport._factories
    primary = None
    try:
        with factories.labjack() as jack:
            raw = factories.mirror(jack, dio_pin=source["mirror_dio_pin"])
            class Mirror:
                async def move_to(self, x, y):
                    if not has_owner(workspace._ownership, "Intensity map"):
                        raise PermissionError("Mirror lease lost")
                    raw.move(x, y)
                    workspace._mirror_last_commanded = (x, y)
                async def home(self):
                    await self.move_to(source["home_x_voltage_v"], source["home_y_voltage_v"])
            mirror = Mirror()
            try:
                yield mirror
            except BaseException as error:
                primary = error
                raise
            finally:
                if home_on_exit:
                    try:
                        await mirror.home()
                    except BaseException as error:
                        if primary is not None:
                            primary.add_note(f"Mirror home failed: {error!r}")
                        else:
                            raise
    except BaseException as error:
        workspace._mirror_last_commanded = None
        if not isinstance(error, asyncio.CancelledError) or getattr(error, "__notes__", None):
            workspace._hardware_fault = f"Mirror operation/cleanup failed: {error!r}"
        raise


def move_manual(workspace, x, y, *, stop=None):
    x, y, _ = validate_position(workspace, x, y)
    if not all(has_owner(workspace._ownership, owner) for owner in ("Spectrum", "Intensity map")):
        raise PermissionError("Manual movement requires both optical workflow leases")
    stop = stop or Event()
    async def move():
        if stop.is_set():
            raise asyncio.CancelledError()
        async with open_workspace_mirror(workspace, home_on_exit=False) as mirror:
            if stop.is_set():
                raise asyncio.CancelledError()
            await mirror.move_to(x, y)
    asyncio.run(move())
    return {"x_voltage_v": x, "y_voltage_v": y, "position_kind": "last commanded, not readback",
            "configuration_id": workspace.plan.configuration_id}


def positioned_spectrum(workspace, settings, position, *, stop=None):
    """Mirror and HORIBA created/called/cleaned on the existing spectrum worker."""
    from labtools.runtime.operator_spectrum import ensure_operator_spectrum

    x, y, settle = validate_position(workspace, *position)
    workspace.workflows.spectrum_settings(settings)
    if not all(has_owner(workspace._ownership, owner) for owner in ("Spectrum", "Intensity map")):
        raise PermissionError("Positioned spectrum requires both optical workflow leases")
    stop = stop or Event()
    runtime = ensure_operator_spectrum(workspace)
    async def operation(job_cancelled):
        def cancelled():
            return stop.is_set() or job_cancelled()
        if cancelled():
            raise asyncio.CancelledError()
        async with open_workspace_mirror(workspace, home_on_exit=True) as mirror:
            if cancelled():
                raise asyncio.CancelledError()
            await mirror.move_to(x, y)
            deadline = time.monotonic() + settle
            while time.monotonic() < deadline:
                if cancelled():
                    raise asyncio.CancelledError()
                await asyncio.sleep(min(0.02, max(0, deadline - time.monotonic())))
            if cancelled():
                raise asyncio.CancelledError()
            async with runtime.service.operation(settings, cancel_requested=cancelled) as spectra:
                return await spectra.acquire(settings, cancel_requested=cancelled)
    job = runtime.worker.submit_operation(settings, operation, owner="sequence-positioned-spectrum")
    while not job.done():
        if stop.wait(0.01):
            job.cancel()
    try:
        return job.result()
    except asyncio.CancelledError:
        raise
    except BaseException as error:
        if getattr(workspace, "all_hardware_enabled", False):
            workspace._hardware_fault = f"Positioned spectrum operation/cleanup failed: {error!r}"
        raise
