"""Fake-device regression tests for opt-in shared LabJack map ownership."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Event, get_ident

import pytest

from labtools.acquisition.intensity_map import (
    acquire_intensity_map,
    config_from_resume_directory,
)
from labtools.config.intensity_map import IntensityMapConfig
from labtools.runtime.labjack_service import (
    LabJackWiring,
    create_labjack_session,
    open_labjack_service,
)
from labtools.runtime.session import ResourceBusyError
from labtools.runtime.shared_map import SharedMapProvider


@pytest.fixture
def config(tmp_path):
    return IntensityMapConfig(
        x_start_v=-1.0,
        x_stop_v=1.0,
        x_points=2,
        y_start_v=-1.0,
        y_stop_v=1.0,
        y_points=2,
        integration_time_s=0.01,
        settle_time_s=0.0,
        output_root=tmp_path,
        backend="simulation",
        simulation_realtime=False,
        save_results=False,
        checkpoint_every_points=100,
    )


def rig(*, failure=None, entered=None, unblock=None):
    calls = []
    state = {"x": 0.0, "y": 0.0, "gate": False, "counts": 0}

    def record(name):
        calls.append((name, get_ident()))
        if name == failure:
            raise OSError("injected " + name)

    class Device:
        def __init__(self):
            record("connect")

        def close(self):
            record("device close")

    class Mirror:
        def __init__(self, device, *, dio_pin):
            assert dio_pin == 2
            record("mirror construct")

        def move(self, x, y):
            record("move")
            state.update(x=x, y=y)

        def home(self):
            record("home")
            state.update(x=0.0, y=0.0)

    class Gate:
        def __init__(self, device, *, pin):
            assert pin == 0
            record("gate construct")

        def open(self):
            record("gate open")
            state["gate"] = True

        def close(self):
            record("gate close")
            state["gate"] = False

    def factory():
        return open_labjack_service(
            device_factory=Device, mirror_factory=Mirror, gate_factory=Gate
        )

    class Counter:
        def configure_channel(self, *args, **kwargs):
            record("configure")

        def get_simultaneous_counts(self, channels, duration):
            record("count")
            assert state["gate"]
            if entered is not None:
                entered.set()
                assert unblock.wait(5)
            state["counts"] += 1
            return {
                c: int((state["x"] + 2) * 10 + (state["y"] + 2) * 5 + c)
                for c in channels
            }

    @contextmanager
    def counter(config):
        record("counter connect")
        try:
            yield Counter()
        finally:
            record("counter close")

    session = create_labjack_session(service_factory=factory)
    provider = SharedMapProvider(
        session, backend="simulation", counter_provider=counter
    )
    return session, provider, calls, state


def names(calls):
    return [n for n, thread in calls]


def test_manual_map_manual_reuses_one_connection(config):
    session, provider, calls, state = rig()
    with session:
        assert calls == []
        with session.reserve("manual", ["mirror"]) as lease:
            lease.call("mirror", "move", 0.5, -0.5)
        result = acquire_intensity_map(config, device_provider=provider)
        assert result.complete
        assert session.reservations() == {}
        assert not state["gate"]
        with session.reserve("manual", ["mirror"]) as lease:
            lease.call("mirror", "move", 0.25, 0.75)
        assert names(calls).count("connect") == 1
        assert "device close" not in names(calls)
    assert names(calls).count("device close") == 1
    hardware_threads = {
        t
        for n, t in calls
        if n not in {"counter connect", "configure", "count", "counter close"}
    }
    assert len(hardware_threads) == 1 and get_ident() not in hardware_threads
    assert {t for n, t in calls if n == "count"} == {get_ident()}


def test_reservation_covers_map_and_cleanup(config):
    session, provider, calls, state = rig()
    with session:

        def progress(snapshot):
            with pytest.raises(ResourceBusyError):
                session.reserve("manual", ["mirror"])
            with pytest.raises(ResourceBusyError):
                session.reserve("other gate", ["gate"])
            with pytest.raises(ResourceBusyError):
                session.close()

        acquire_intensity_map(
            config, device_provider=provider, progress_callback=progress
        )
        order = names(calls)
        assert (
            order.index("home")
            < order.index("gate close")
            < order.index("counter close")
        )
        with session.reserve("manual", ["mirror"]):
            pass


@pytest.mark.parametrize(
    "failure", ["move", "home", "gate open", "gate close", "count", "configure"]
)
def test_failure_cleanup_attempts_and_fault_policy(config, failure):
    session, provider, calls, state = rig(failure=failure)
    with session:
        with pytest.raises(Exception):
            acquire_intensity_map(config, device_provider=provider)
        order = names(calls)
        assert "counter close" in order
        assert session.reservations() == {}
        if failure != "configure":
            assert "home" in order and "gate close" in order
            assert (
                order.index("home")
                < order.index("gate close")
                < order.index("counter close")
            )
        if failure in {"move", "home", "gate open", "gate close"}:
            with pytest.raises(RuntimeError, match="faulted"):
                session.reserve("manual", ["mirror"])
        else:
            with session.reserve("manual", ["mirror"]):
                pass
        # Stop fault injection before session close so teardown is not the test error.
        if failure == "gate close":
            session._devices["labjack"]._gate.close = lambda: calls.append(
                ("gate close retry", get_ident())
            )


def test_primary_error_survives_home_failure_and_gate_is_attempted(config):
    session, provider, calls, state = rig(failure="move")
    with session:
        # Construct first, then inject an additional cleanup failure.
        with session.reserve("manual", ["mirror"]) as lease:
            lease.call("gate", "open_gate")
        service = session._devices["labjack"]

        def bad_home():
            calls.append(("home failed", get_ident()))
            raise OSError("home failed")

        service._mirror.home = bad_home
        with pytest.raises(OSError, match="injected move") as caught:
            acquire_intensity_map(config, device_provider=provider)
        assert "gate close" in names(calls)
        assert not state["gate"]
        assert any("home failed" in n for n in caught.value.__notes__)


def test_cancel_and_resume_same_session(config):
    session, provider, calls, state = rig()
    with session:
        first = acquire_intensity_map(
            config,
            device_provider=provider,
            cancel_requested=lambda: state["counts"] >= 1,
        )
        assert not first.complete
        assert not state["gate"]
        restored = config_from_resume_directory(first.output_directory)
        second = acquire_intensity_map(
            restored, resume_directory=first.output_directory, device_provider=provider
        )
        assert second.complete
        assert names(calls).count("connect") == 1
        assert state["counts"] == config.x_points * config.y_points


@pytest.mark.parametrize(
    "change", [{"backend": "real"}, {"mirror_dio_pin": 4}, {"spad_gate_pin": 1}]
)
def test_backend_wiring_mismatch_before_connection(config, change):
    session, provider, calls, state = rig()
    with session:
        with pytest.raises(ValueError), provider(replace(config, **change)):
            pass
        assert calls == [] and session.reservations() == {}


def test_counter_open_failure_does_not_open_labjack(config):
    session, provider, calls, state = rig()

    @contextmanager
    def bad_counter(config):
        raise OSError("counter connect failed")
        yield

    provider.counter_provider = bad_counter
    with session:
        with pytest.raises(OSError), provider(config):
            pass
        assert not calls and session.reservations() == {}


def test_inflight_counter_still_reserves_labjack(config):
    entered, unblock = Event(), Event()
    session, provider, calls, state = rig(entered=entered, unblock=unblock)
    with session, ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            acquire_intensity_map, config, device_provider=provider
        )
        try:
            assert entered.wait(4)
            with pytest.raises(ResourceBusyError):
                session.reserve("manual", ["mirror"])
            with pytest.raises(ResourceBusyError):
                session.close()
        finally:
            unblock.set()
        assert future.result(timeout=10).complete


@pytest.mark.parametrize(
    "wiring",
    [
        LabJackWiring(2, 2),
        LabJackWiring(2, 3),
        LabJackWiring(-1, 0),
        LabJackWiring(15, 0),
        LabJackWiring(2, 16),
        LabJackWiring(True, 0),
    ],
)
def test_bad_wiring_before_factory(wiring):
    with pytest.raises(ValueError):
        create_labjack_session(
            wiring, service_factory=lambda: pytest.fail("must not construct")
        )


def test_service_bounds_and_thread_affinity():
    session, provider, calls, state = rig()
    with session:
        with session.reserve("manual", ["mirror"]) as lease:
            lease.call("mirror", "move", 1.0, 2.0)
            service = session._devices["labjack"]
            with pytest.raises(RuntimeError, match="owning"):
                service.move(0.0, 0.0)
            with pytest.raises(ValueError):
                lease.call("mirror", "move", 11.0, 0.0)
            with pytest.raises(RuntimeError, match="faulted"):
                lease.call("mirror", "move", 0.0, 0.0)
            lease.cleanup("gate", "close_gate")
        assert names(calls).count("move") == 1


def test_partial_factory_failure_closes_device_and_preserves_error():
    calls = []

    class Device:
        def close(self):
            calls.append("close")
            raise OSError("close failed")

    def bad_mirror(*args, **kwargs):
        raise ValueError("construct failed")

    with pytest.raises(ValueError, match="construct failed") as caught:
        open_labjack_service(
            device_factory=Device, mirror_factory=bad_mirror, gate_factory=object
        )
    assert calls == ["close"]
    assert "close failed" in caught.value.__notes__[0]


def test_service_shutdown_closes_device_even_if_gate_close_fails():
    session, provider, calls, state = rig(failure="gate close")
    with pytest.raises(ExceptionGroup), session:
        with session.reserve("manual", ["mirror"]) as lease:
            lease.call("mirror", "move", 0.0, 0.0)
    assert names(calls)[-2:] == ["gate close", "device close"]
    assert "home" not in names(calls)


def test_imports_without_native_dependencies(tmp_path):
    code = """
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('labtools.devices', 'u6', 'PyQt6', 'zmq', 'horiba_sdk')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from labtools.runtime.labjack_service import create_labjack_session
from labtools.runtime.shared_map import SharedMapProvider
with create_labjack_session(): pass
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_checkpoint_failure_still_cleans_up_under_reservation(config, monkeypatch):
    from labtools.acquisition import intensity_map

    session, provider, calls, state = rig()
    original_save = intensity_map._save_checkpoint

    def save(*args, **kwargs):
        if "gate open" in names(calls):
            if "counter close" not in names(calls):
                with pytest.raises(ResourceBusyError):
                    session.reserve("manual", ["mirror"])
            raise OSError("checkpoint disk error")
        return original_save(*args, **kwargs)

    monkeypatch.setattr(intensity_map, "_save_checkpoint", save)
    with session:
        with pytest.raises(ExceptionGroup):
            acquire_intensity_map(config, device_provider=provider)
        assert "home" in names(calls) and "gate close" in names(calls)
        assert not state["gate"]
        assert session.reservations() == {}


def test_gate_cleanup_inflight_keeps_whole_measurement_reserved(config):
    entered, finish = Event(), Event()
    session, provider, calls, state = rig()
    with session:
        # Open the service before replacing its gate-close for deterministic timing.
        with session.reserve("manual", ["mirror"]) as lease:
            lease.call("mirror", "move", 0.0, 0.0)
        gate = session._devices["labjack"]._gate
        original_close = gate.close

        def close():
            entered.set()
            assert finish.wait(5)
            original_close()

        gate.close = close
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                acquire_intensity_map, config, device_provider=provider
            )
            try:
                assert entered.wait(4)
                with pytest.raises(ResourceBusyError):
                    session.reserve("manual", ["mirror"])
                with pytest.raises(ResourceBusyError):
                    session.reserve("gate", ["gate"])
            finally:
                finish.set()
            assert future.result(timeout=10).complete
        assert session.reservations() == {}


def test_simulation_requires_explicit_counter_provider():
    session, _, _, _ = rig()
    with session, pytest.raises(ValueError, match="explicit"):
        SharedMapProvider(session, backend="simulation")


def test_counter_close_error_does_not_replace_measurement_error(config):
    session, provider, calls, state = rig()

    @contextmanager
    def counter(config):
        class Counter:
            def configure_channel(self, *a, **k):
                pass

            def get_simultaneous_counts(self, *a, **k):
                raise ValueError("primary count failure")

        try:
            yield Counter()
        finally:
            raise OSError("counter close failure")

    provider.counter_provider = counter
    with session:
        with pytest.raises(ValueError, match="primary count failure") as caught:
            acquire_intensity_map(config, device_provider=provider)
        assert any("counter close failure" in n for n in caught.value.__notes__)
        assert "home" in names(calls) and "gate close" in names(calls)
        assert session.reservations() == {}
