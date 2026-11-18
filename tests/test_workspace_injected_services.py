"""Resource-specific injection, ownership and thread/loop lifecycle evidence."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import get_ident

import pytest

from labtools.acquisition.intensity_map import IntensityMapConfig
from labtools.config.spectrum import SpectrumSettings
from labtools.simulation.ownership import WorkspaceOwnership
from labtools.simulation.workspace_services import InjectedSimulationServices


def settings():
    return SpectrumSettings(configuration_id="toy-scene-v1", backend="simulation", preset="syncerity",
                            exposure_s=.065, gain=0, speed=0, slit_width_mm=.1, start_nm=500, end_nm=600)


def map_config(tmp_path):
    return IntensityMapConfig(x_start_v=-1, x_stop_v=1, y_start_v=-1, y_stop_v=1, x_points=2, y_points=2, backend="simulation", output_root=tmp_path,
                              integration_time_s=.001, settle_time_s=0, save_results=False)


@pytest.fixture
def bound_services():
    ownership = WorkspaceOwnership()
    services = InjectedSimulationServices()
    services.bind(ownership)
    try:
        yield ownership, services
    finally:
        ownership.close()


def test_unbound_and_unreserved_operations_refused(tmp_path, bound_services):
    services = InjectedSimulationServices()
    with pytest.raises(RuntimeError, match="Bind"):
        services.acquire_map(map_config(tmp_path))
    _, bound = bound_services
    with pytest.raises(PermissionError):
        bound.acquire_map(map_config(tmp_path))
    with pytest.raises(PermissionError):
        asyncio.run(bound.spectrum.acquire(settings()))
    assert not bound.events()


def test_real_requests_refused_before_provider(tmp_path, bound_services):
    _, services = bound_services
    with pytest.raises(ValueError, match="real hardware"):
        services.acquire_map(replace(map_config(tmp_path), backend="real"))
    with pytest.raises(ValueError):
        asyncio.run(services.spectrum.acquire(replace(settings(), backend="real")))
    assert not services.events()


def test_map_worker_affinity_and_cleanup_before_release(tmp_path, bound_services):
    ownership, services = bound_services
    caller = get_ident()
    with ownership.reserve("Intensity map"):
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(services.acquire_map, map_config(tmp_path)).result()
        assert result.complete
        events = services.events()
        assert len({event["thread"] for event in events}) == 1
        assert events[0]["thread"] != caller
        assert {event["resource"] for event in events} == {"mirror", "gate", "counter"}
        assert [event["action"] for event in events[-3:]] == ["closed"] * 3
        assert ownership.status().resources[0].owner == "Intensity map"
    assert ownership.status().resources[0].owner is None


def test_cancelled_map_closes_resources_and_can_repeat(tmp_path, bound_services):
    ownership, services = bound_services
    with ownership.reserve("Intensity map"):
        result = services.acquire_map(map_config(tmp_path), cancel_requested=lambda: True)
        assert not result.complete
        assert [event["action"] for event in services.events()[-3:]] == ["closed"] * 3
    with ownership.reserve("Intensity map"):
        assert services.acquire_map(map_config(tmp_path)).complete


def test_map_failure_closes_resources_and_does_not_replace_error(tmp_path, bound_services):
    ownership, services = bound_services
    primary = ValueError("progress failed")

    def fail(snapshot):
        raise primary

    with ownership.reserve("Intensity map"):
        with pytest.raises(ValueError) as caught:
            services.acquire_map(map_config(tmp_path), progress_callback=fail)
        assert caught.value is primary
        assert [event["action"] for event in services.events()[-3:]] == ["closed"] * 3


def test_same_spectrum_service_reused_without_cross_loop_handles(bound_services):
    ownership, services = bound_services
    service = services.spectrum
    for _ in range(2):
        with ownership.reserve("Spectrum"):
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(lambda: asyncio.run(service.acquire(settings()))).result()
            assert result.settings.backend == "simulation"
            assert ownership.status().resources[0].owner == "Spectrum"
    events = services.events()
    groups = []
    for event in events:
        if event["action"] == "open":
            groups.append([])
        groups[-1].append(event)
    assert len(groups) == 2
    for group in groups:
        assert group[-1]["action"] == "closed"
        assert len({(event["thread"], event["loop"]) for event in group}) == 1
        assert group[0]["loop"] is not None


def test_dark_capture_subtraction_and_cancellation_reuse(bound_services):
    ownership, services = bound_services

    async def workflow():
        dark = await services.spectrum.capture_dark(settings())
        result = await services.spectrum.acquire(settings(), dark_mode="pre_taken", dark=dark)
        assert result.dark_record_id == dark.record_id
        with pytest.raises(asyncio.CancelledError):
            await services.spectrum.acquire(settings(), cancel_requested=lambda: True)
        return await services.spectrum.acquire(settings())

    with ownership.reserve("Spectrum"):
        assert asyncio.run(workflow()).settings.backend == "simulation"
    assert services.events()[-1]["action"] == "closed"


def test_bind_is_single_workspace_only(bound_services):
    ownership, services = bound_services
    with pytest.raises(RuntimeError, match="already bound"):
        services.bind(ownership)


def test_map_proxy_rejects_wrong_thread_and_closed_handle(tmp_path, bound_services):
    ownership, services = bound_services
    with ownership.reserve("Intensity map"):
        with (
            services._map_backend(map_config(tmp_path)) as (mirror, _gate, _counter),
            ThreadPoolExecutor(max_workers=1) as executor,
            pytest.raises(RuntimeError, match="thread/lifetime"),
        ):
            executor.submit(mirror.move, 0, 0).result()
        with pytest.raises(RuntimeError, match="thread/lifetime"):
            mirror.move(0, 0)


def test_detector_proxy_rejects_reuse_after_context_exit(bound_services):
    ownership, services = bound_services

    async def workflow():
        async with services._spectrum_backend(settings()) as detector:
            await detector.capture_dark()
        with pytest.raises(RuntimeError, match="thread/loop/lifetime"):
            await detector.acquire("none")

    with ownership.reserve("Spectrum"):
        asyncio.run(workflow())


def test_actual_injected_workspace_affinity_and_cleanup(tmp_path):
    import importlib.util
    import os
    import subprocess
    import sys
    from pathlib import Path

    if importlib.util.find_spec("PyQt6") is None:
        pytest.skip("PyQt6 unavailable: injected workspace GUI execution remains unassessed")
    root = Path(__file__).resolve().parents[1]
    code = r'''
import builtins, sys, time
from pathlib import Path
from threading import get_ident
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if any(name==p or name.startswith(p+".") for p in ("labtools.devices","horiba_sdk","u6","pyvisa","serial")):
        raise AssertionError("Native import forbidden: "+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from PyQt6.QtWidgets import QApplication
from labtools.gui.workspace import SimulationWorkspace
from labtools.simulation.workspace import busy_workflows
from labtools.simulation.workspace_services import InjectedSimulationServices
app=QApplication([]); ui_thread=get_ident()
services=InjectedSimulationServices()
w=SimulationWorkspace(output_root=Path(sys.argv[1]),map_acquisition=services.acquire_map,spectrum_service=services.spectrum)
services.bind(w.ownership)
m=w.pages["Intensity map"]; s=w.pages["Spectrum"]
errors=[];m.map_controller.failed.connect(lambda *a:errors.append(a));s._show_error=lambda *a:errors.append(a)
def wait(predicate):
    end=time.monotonic()+20
    while not predicate():
        app.processEvents();time.sleep(.005)
        assert time.monotonic()<end,"Injected workflow did not finish"
    app.processEvents()
try:
    m.x_points.setValue(20);m.y_points.setValue(20);m.integration.setValue(.02);m.settle.setValue(0)
    m.start_new();wait(lambda:m.progress.value()>0 or not m.map_controller.busy)
    assert m.map_controller.busy
    s.acquire_spectrum();assert "Workspace busy" in s.status.text()
    w.stop_all();wait(lambda:not busy_workflows(w.pages))
    assert w.ownership.status().resources[0].owner is None
    assert all(e["thread"]!=ui_thread for e in services.events())
    assert [e["action"] for e in services.events()[-3:]]==["closed"]*3
    s.acquire_spectrum();wait(lambda:not busy_workflows(w.pages))
    assert s.latest_result is not None and not errors
    detector=[e for e in services.events() if e["workflow"]=="Spectrum"]
    assert detector[0]["action"]=="open" and detector[-1]["action"]=="closed"
    assert len({(e["thread"],e["loop"]) for e in detector})==1
    assert detector[0]["thread"]!=ui_thread
    assert w.ownership.status().resources[0].owner is None
    assert w.close()
    print("INJECTED WORKSPACE AFFINITY PASSED")
finally:
    if busy_workflows(w.pages):w.stop_all();wait(lambda:not busy_workflows(w.pages))
    w.close();app.processEvents()
'''
    env = dict(os.environ, PYTHONPATH=str(root / "src"), QT_QPA_PLATFORM="offscreen", MPLBACKEND="Agg")
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=root, env=env,
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "INJECTED WORKSPACE AFFINITY PASSED" in result.stdout
