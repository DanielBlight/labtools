"""Qt-free anneal programs, shared-worker cubes and exclusive repeat sequences."""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import numpy as np

from labtools.runtime.workflow_batch import Batch


def unique_directory(root, prefix):
    path = Path(root) / (prefix + "-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, default=str, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def run_program(workspace, program, *, stop=None, report=lambda text: None, output=None, save_output=True):
    stop = stop or Event()
    points = program.points()
    # Validate every dose against the existing source/local profile before any I/O.
    for point in points:
        if getattr(workspace, "all_hardware_enabled", False):
            workspace.anneal_config(point)
        else:
            workspace.drafts.validate("anneal", point)
    folder = (output or unique_directory(program.base.output_root, "anneal-program")) if save_output else None
    record = {"configuration_id": workspace.plan.configuration_id, "mode": program.mode, "spacing": program.spacing,
              "status": "running", "completed_points": 0, "points": [asdict(p) for p in points], "point_results": []}
    if folder is not None:
        write_json(folder / "program.json", {k: v for k, v in record.items() if k != "point_results"})
    try:
        for i, point in enumerate(points):
            if stop.is_set():
                break
            report(f"Annealing point {i + 1}/{len(points)}; dwell {point.point_dwell_s:g} s")
            if stop.is_set():
                break
            # Each dose uses the accepted full shutter/stage/cleanup lifecycle.
            result = workspace.acquire_anneal(replace(point, output_root=folder / f"point-{i+1:05d}" if folder else point.output_root,
                                                      save_run_log=point.save_run_log and save_output), stop_event=stop)
            record["point_results"].append({"point_index": i, "settings": point, "result": result})
            if result.stopped:
                stop.set()
                break
            if not result.completed:
                raise RuntimeError("Annealing did not complete; refusing the next point/measurement")
            record["completed_points"] += 1
            if folder is not None:
                write_json(folder / "program.json", {k: v for k, v in record.items() if k != "point_results"})
        record["status"] = "cancelled" if stop.is_set() else "completed"
    except BaseException as error:
        record.update(status="failed", error=repr(error))
        error.retained_run = record
        raise
    finally:
        if folder is not None:
            write_json(folder / "program.json", {k: v for k, v in record.items() if k != "point_results"})
    return record


def validate_cube(workspace, config):
    config.validate()
    workspace._require_open()
    if getattr(workspace, "all_hardware_enabled", False):
        workspace.hardware_ready()
    workspace.plan.verify_sources()
    if config.configuration_id != workspace.plan.configuration_id:
        raise ValueError("Cube configuration must match the workspace")
    workspace.workflows.spectrum_settings(config.spectrum)
    base = workspace.plan.map_config
    for value in (config.x_start_v, config.x_stop_v, config.y_start_v, config.y_stop_v):
        if not base.safe_voltage_min_v <= value <= base.safe_voltage_max_v:
            raise ValueError("Hyperspectral mirror position exceeds source limits")
    if config.x_points * config.y_points > 100000:
        raise ValueError("Cube exceeds 100000 pixels")
    if config.dark_mode == "pre_taken":
        raise ValueError("Unified cubes support none/per_center/per_frame dark; reusable dark is not selected here")
    if not getattr(workspace, "simulation_only", False) and not getattr(workspace, "all_hardware_enabled", False):
        raise RuntimeError("Real hyperspectral mapping requires --hardware, not HORIBA-only mode")


@asynccontextmanager
async def cube_mirror(workspace):
    if getattr(workspace, "simulation_only", False):
        from labtools.simulation.hyperspectral import (
            open_simulated_hyperspectral_mirror,
        )

        async with open_simulated_hyperspectral_mirror() as mirror:
            yield mirror
    else:
        from labtools.runtime.workflow_batch import has_owner

        if not has_owner(workspace._ownership, "Intensity map"):
            raise PermissionError("Cube mirror requires the map resource lease")
        factories = workspace._map_transport._factories
        base = workspace.plan.map_config
        # No IDQ or gate acquisition is needed for a spectral cube.
        with factories.labjack() as jack:
            mirror = factories.mirror(jack, dio_pin=base.mirror_dio_pin)

            class Mirror:
                backend_identity = "real:workspace-labjack-mirror-v1"

                async def move_to(self, x, y):
                    if not has_owner(workspace._ownership, "Intensity map"):
                        raise PermissionError("Cube mirror lease lost")
                    mirror.move(x, y)

                async def home(self):
                    mirror.move(workspace.plan.hardware_settings["home_x_voltage_v"], workspace.plan.hardware_settings["home_y_voltage_v"])

            adapter = Mirror()
            primary = None
            try:
                yield adapter
            except BaseException as error:
                primary = error
                raise
            finally:
                try:
                    await adapter.home()
                except BaseException as cleanup:
                    if primary is not None:
                        primary.add_note(f"Cube mirror home failed: {cleanup!r}")
                    else:
                        raise


def run_cube(workspace, config, *, stop=None, output_path=None, progress=None, display=None):
    from labtools.runtime.hyperspectral import open_hyperspectral_service
    from labtools.runtime.operator_spectrum import ensure_operator_spectrum

    validate_cube(workspace, config)
    from labtools.runtime.workflow_batch import has_owner

    if not all(has_owner(workspace._ownership, owner) for owner in ("Spectrum", "Intensity map")):
        raise PermissionError("Hyperspectral mapping requires both Spectrum and map resource leases")
    stop = stop or Event()
    if stop.is_set():
        raise asyncio.CancelledError()
    runtime = ensure_operator_spectrum(workspace)

    integrated = np.full((config.y_points, config.x_points), np.nan)
    def pixel(iy, ix, wavelength, intensity):
        integrated[iy, ix] = float(np.sum(intensity))
        if display is not None:
            image = integrated.copy()
            image.setflags(write=False)
            display("cube-live", (image, wavelength, intensity, iy, ix))

    async def operation(job_cancelled):
        def cancelled():
            return job_cancelled() or stop.is_set()
        async with open_hyperspectral_service(config, spectrum_service=runtime.service,
                                             mirror_factory=lambda: cube_mirror(workspace), cancel_requested=cancelled) as service:
            return await service.acquire(config, output_path=output_path, progress=progress, cancel_requested=cancelled, pixel_callback=pixel)

    job = runtime.worker.submit_operation(config.spectrum, operation, owner="Hyperspectral")
    while not job.done():
        if stop.wait(0.01):
            job.cancel()
    try:
        result = job.result()
    except asyncio.CancelledError:
        raise
    except BaseException as error:
        if getattr(workspace, "all_hardware_enabled", False):
            workspace._hardware_fault = f"Hyperspectral operation/cleanup failed: {error!r}"
        raise
    if result.status == "cancelled":
        stop.set()
    return result


def run_sequence(workspace, program, measurement, request, *, cycles, output_root=None,
                 save_output=True, stop=None, report=lambda text: None, display=None):
    """One baseline measurement, then one anneal/measurement pair per cycle."""
    from labtools.runtime.operator_spectrum import ensure_operator_spectrum

    if type(cycles) is not int or not 1 <= cycles <= 10000:
        raise ValueError("Cycles must be an integer between 1 and 10000")
    if measurement not in {"Spectrum", "Intensity map", "Hyperspectral"}:
        raise ValueError("Unknown sequence measurement")
    points = program.points()
    if not program.base.return_rotation_stage:
        raise ValueError("Sequences require return rotation stage enabled before measurement")
    for point in points:
        workspace.anneal_config(point) if getattr(workspace, "all_hardware_enabled", False) else workspace.drafts.validate("anneal", point)
    if measurement == "Hyperspectral":
        validate_cube(workspace, request)
    elif measurement == "Spectrum":
        workspace.workflows.spectrum_settings(request)
    else:
        workspace.workflows.map_config(request)
    if save_output and (output_root is None or not str(output_root).strip()):
        raise ValueError("Choose a sequence output folder or disable Save results")
    stop = stop or Event()
    batch = Batch(workspace._ownership, ("Annealing", "Spectrum", "Intensity map"))
    folder = None
    record = {"configuration_id": workspace.plan.configuration_id, "measurement": measurement, "status": "running",
              "steps": [], "cycles": cycles, "baseline_measurement": True, "save_output": save_output,
              "anneal_program": asdict(program), "measurement_request": asdict(request), "retained_steps": []}
    def persist():
        if folder is not None:
            write_json(folder / "sequence.json", {k: v for k, v in record.items() if k != "retained_steps"})
    try:
        if save_output:
            folder = unique_directory(output_root, "sequence")
        persist()
        plan = [(0, measurement, "baseline")]
        for cycle in range(1, cycles + 1):
            plan.extend(((cycle, "Annealing", "anneal"), (cycle, measurement, "post-anneal")))
        for cycle, phase, role in plan:
            if stop.is_set():
                break
            report("Baseline measurement before first anneal" if role == "baseline" else f"Cycle {cycle}/{cycles}: {phase}")
            step = folder / f"{cycle:04d}-{role}" if folder else None
            if step is not None:
                step.mkdir()
            if phase == "Annealing":
                with batch.borrow("Annealing"):
                    result = run_program(workspace, program, stop=stop, report=report, output=step, save_output=save_output)
                if result["status"] != "completed":
                    stop.set()
            elif phase == "Spectrum":
                with batch.borrow("Spectrum"):
                    result = asyncio.run(ensure_operator_spectrum(workspace).facade.acquire(request, cancel_requested=stop.is_set))
                if step is not None:
                    np.savez_compressed(step / "spectrum.npz", wavelength_nm=result.wavelength_nm, intensity=result.intensity)
                if display is not None:
                    display("spectrum", result)
            elif phase == "Intensity map":
                def map_progress(snapshot):
                    if display is not None:
                        display("map", snapshot)
                with batch.borrow("Intensity map"):
                    result = workspace.acquire_map(replace(request, output_root=step or request.output_root, save_results=save_output),
                        cancel_requested=stop.is_set, memory_only=not save_output, progress_callback=map_progress)
                if not result.complete:
                    stop.set()
                if display is not None:
                    display("map", result)
            else:
                with batch.borrow("Spectrum"), batch.borrow("Intensity map"):
                    result = run_cube(workspace, request, stop=stop, output_path=step / "cube.npz" if step else None, display=display)
                if display is not None:
                    display("cube", result)
            record["retained_steps"].append({"cycle": cycle, "phase": phase, "role": role, "result": result})
            record["steps"].append({"cycle": cycle, "phase": phase, "role": role, "output": str(step) if step else None,
                                    "status": "cancelled" if stop.is_set() else "completed"})
            persist()
        record["status"] = "cancelled" if stop.is_set() else "completed"
    except asyncio.CancelledError:
        record["status"] = "cancelled"
    except BaseException as error:
        record.update(status="failed", error=repr(error))
        error.retained_run = record
        raise
    finally:
        try:
            persist()
        finally:
            batch.release()
    return record
