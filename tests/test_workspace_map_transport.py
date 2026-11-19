"""Actual map provider/acquisition with fake transports; native imports forbidden."""

import builtins
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import get_ident

import pytest

from labtools.config.intensity_map import IntensityMapConfig
from labtools.config.workspace import WorkspaceConfig
from labtools.runtime.map_devices import MapTransportFactories, open_map_devices
from labtools.runtime.workspace_map_transport import WorkspaceMapTransport
from labtools.simulation.ownership import WorkspaceOwnership


@pytest.fixture
def rig(tmp_path, monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "u6", "serial", "pyvisa", "horiba_sdk")):
            raise AssertionError("Native import forbidden: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    ownership = WorkspaceOwnership(WorkspaceConfig(configuration_id="fake-map"))
    config = IntensityMapConfig(-1, 1, 2, -1, 1, 2, integration_time_s=.001,
                                settle_time_s=0, backend="real", save_results=False,
                                time_controller_address="fake-counter", output_root=tmp_path)
    events = []
    failures = set()
    primary = ValueError("fake operation failed")

    class Device:
        def __init__(self, name):
            self.name = name
            self.thread = get_ident()
            self.closed = False
            self.record("construct")

        def record(self, action):
            assert get_ident() == self.thread and not self.closed
            events.append((self.name, action, self.thread))
            if (self.name, action) in failures:
                if action in {"exit", "home", "close"}:
                    raise OSError(f"{self.name} {action} failed")
                raise primary

        def __enter__(self):
            self.record("enter")
            return self

        def __exit__(self, *args):
            try:
                self.record("exit")
            finally:
                self.closed = True

    class Mirror(Device):
        def move(self, x, y):
            self.record("move")

        def home(self):
            self.record("home")

    class Gate(Device):
        def open(self):
            self.record("open")

        def close(self):
            self.record("close")

    class Counter(Device):
        def configure_channel(self, *args, **kwargs):
            self.record("configure")

        def get_simultaneous_counts(self, channels, integration_time_s):
            self.record("read")
            return dict.fromkeys(channels, 7)

    def jack():
        return Device("jack")

    def counter(address):
        assert address == "fake-counter"
        return Counter("counter")

    def mirror(labjack, *, dio_pin):
        assert labjack.name == "jack" and dio_pin == config.mirror_dio_pin
        return Mirror("mirror")

    def gate(labjack, *, pin):
        assert labjack.name == "jack" and pin == config.spad_gate_pin
        return Gate("gate")

    factories = MapTransportFactories(jack, counter, mirror, gate)
    boundary = WorkspaceMapTransport(ownership=ownership, configuration_id="fake-map", factories=factories)
    try:
        yield ownership, boundary, config, events, failures, primary, factories
    finally:
        ownership.close()


def test_refusal_before_construction(rig):
    ownership, boundary, config, events, _, _, factories = rig
    with pytest.raises(PermissionError):
        boundary.acquire(config)
    with pytest.raises(ValueError):
        boundary.acquire(replace(config, backend="simulation"))
    with pytest.raises(ValueError):
        WorkspaceMapTransport(ownership=ownership, configuration_id="wrong", factories=factories)
    with pytest.raises(TypeError):
        WorkspaceMapTransport(ownership=ownership, configuration_id="fake-map", factories=None)
    assert not events


def test_conflicting_spectrum_lease_blocks_map(rig):
    ownership, boundary, config, events, *_ = rig
    with ownership.reserve("Spectrum"), pytest.raises(PermissionError):
        boundary.acquire(config)
    assert not events


def test_complete_repeat_on_worker_and_cleanup_before_release(rig):
    ownership, boundary, config, events, *_ = rig
    caller = get_ident()
    for _ in range(2):
        start = len(events)
        with ownership.reserve("Intensity map"):
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(boundary.acquire, config).result()
            assert result.complete
            operation = events[start:]
            assert len({event[2] for event in operation}) == 1
            assert operation[0][2] != caller
            assert [(e[0], e[1]) for e in operation[-4:]] == [
                ("mirror", "home"), ("gate", "close"), ("counter", "exit"), ("jack", "exit"),
            ]
            assert ownership.status().resources[0].owner == "Intensity map"
        assert ownership.status().resources[0].owner is None


def test_cancel_then_reuse(rig):
    ownership, boundary, config, events, *_ = rig
    with ownership.reserve("Intensity map"):
        result = boundary.acquire(config, cancel_requested=lambda: True)
        assert not result.complete
        assert events[-1][:2] == ("jack", "exit")
        assert ownership.status().resources[0].owner == "Intensity map"
    with ownership.reserve("Intensity map"):
        assert boundary.acquire(config).complete


@pytest.mark.parametrize("failure", [("counter", "enter"), ("mirror", "construct"),
                                     ("gate", "construct"), ("counter", "configure"),
                                     ("mirror", "move"), ("counter", "read")])
def test_partial_start_and_operation_failure_close_acquired_contexts(rig, failure):
    ownership, boundary, config, events, failures, primary, _ = rig
    failures.add(failure)
    with ownership.reserve("Intensity map"):
        with pytest.raises(ValueError) as caught:
            boundary.acquire(config)
        assert caught.value is primary
        assert events[-1][:2] == ("jack", "exit")
        if failure != ("counter", "enter"):
            assert ("counter", "exit") in [event[:2] for event in events]
        assert ownership.status().resources[0].owner == "Intensity map"


def test_competing_home_and_gate_failure_preserves_acquisition_error(rig):
    ownership, boundary, config, events, failures, primary, _ = rig
    failures.update({("counter", "read"), ("mirror", "home"), ("gate", "close")})
    with ownership.reserve("Intensity map"):
        with pytest.raises(ValueError) as caught:
            boundary.acquire(config)
        assert caught.value is primary
        assert any("mirror home" in note for note in primary.__notes__)
        assert any("gate close" in note for note in primary.__notes__)
        assert events[-1][:2] == ("jack", "exit")


def test_context_exit_failures_attempt_all_teardown_without_new_policy(rig):
    ownership, boundary, config, events, failures, *_ = rig
    failures.update({("counter", "exit"), ("jack", "exit")})
    # Preserve ExitStack's existing exception chaining; do not claim primary identity here.
    with ownership.reserve("Intensity map"), pytest.raises(OSError, match="jack exit"):
        boundary.acquire(config)
    assert [event[:2] for event in events[-2:]] == [("counter", "exit"), ("jack", "exit")]


def test_wrong_thread_and_closed_proxy_rejected(rig):
    ownership, boundary, config, _, _, _, _ = rig
    with ownership.reserve("Intensity map"):
        with (
            boundary._backend(config) as (mirror, _gate, _counter),
            ThreadPoolExecutor(max_workers=1) as executor,
            pytest.raises(RuntimeError, match="thread/lifetime"),
        ):
            executor.submit(mirror.move, 0, 0).result()
        with pytest.raises(RuntimeError, match="thread/lifetime"):
            mirror.move(0, 0)


def test_provider_rejects_factories_for_simulation(rig):
    _, _, config, events, _, _, factories = rig
    with pytest.raises(ValueError), open_map_devices(replace(config, backend="simulation"), factories=factories):
        pytest.fail("Provider should reject before construction")
    assert not events
