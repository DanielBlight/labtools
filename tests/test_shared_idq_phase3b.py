"""Phase 3b application-owned IDQ count service tests; no real endpoints."""

from __future__ import annotations

import builtins
from dataclasses import replace
from threading import get_ident

import pytest

from labtools.config.intensity_map import IntensityMapConfig
from labtools.runtime.idq_count_service import canonical_idq_address, idq_resource_name
from labtools.runtime.session import ResourceBusyError
from labtools.runtime.shared_application import SharedMirrorMapApplication


class FakeLabJack:
    def __init__(self, events):
        self.events = events
        events.append(("labjack-connect", get_ident()))

    def move(self, x, y):
        self.events.append(("move", get_ident(), x, y))

    def home(self):
        self.events.append(("home", get_ident()))

    def open_gate(self):
        self.events.append(("gate-open", get_ident()))

    def close_gate(self):
        self.events.append(("gate-close", get_ident()))

    def close(self):
        self.events.append(("labjack-close", get_ident()))


class FakeIDQ:
    def __init__(self, events, *, failure=None):
        self.events = events
        self.failure = failure
        events.append(("idq-connect", get_ident()))
        if failure == "connect":
            raise OSError("idq connect")

    def configure_channel(self, channel, **kwargs):
        self.events.append(("configure", get_ident(), channel, kwargs))
        if self.failure == "configure":
            raise OSError("idq configure")

    def get_simultaneous_counts(self, channels, duration):
        self.events.append(("count", get_ident(), channels, duration))
        if self.failure == "count":
            raise OSError("idq count")
        return {channel: 10 * channel for channel in channels}

    def close(self):
        self.events.append(("idq-close", get_ident()))


@pytest.fixture
def config(tmp_path):
    return IntensityMapConfig(
        x_start_v=0,
        x_stop_v=1,
        x_points=2,
        y_start_v=0,
        y_stop_v=1,
        y_points=2,
        channels=(1, 2),
        channel_thresholds_v=(0.1, 0.2),
        channel_edges=("rising", "falling"),
        integration_time_s=0.01,
        settle_time_s=0,
        output_root=tmp_path,
        backend="real",
        save_results=False,
        checkpoint_every_points=1,
        time_controller_address="169.254.99.159",
    )


def application(events, *, failure=None):
    return SharedMirrorMapApplication(
        backend="real",
        service_factory=lambda: FakeLabJack(events),
        idq_service_factory=lambda: FakeIDQ(events, failure=failure),
        time_controller_address="169.254.99.159",
    )


def test_address_contract_is_ip_only_and_canonical():
    assert canonical_idq_address(" 169.254.99.159 ") == "169.254.99.159"
    assert idq_resource_name("169.254.99.159") == "time-controller:169.254.99.159"
    with pytest.raises(ValueError):
        canonical_idq_address("idq-lab")


def test_distinct_addresses_have_distinct_resource_keys():
    assert idq_resource_name("169.254.99.159") != idq_resource_name("169.254.99.160")


def test_narrow_service_constructs_connects_uses_and_closes_on_worker(config):
    from labtools.runtime.idq_count_service import IDQCountService

    events = []

    class Controller:
        def __init__(self, address):
            events.append(("construct", get_ident(), address))

        def connect(self):
            events.append(("connect", get_ident()))

        def configure_channel(self, channel, **kwargs):
            events.append(("configure", get_ident(), channel, kwargs))

        def get_simultaneous_counts(self, channels, duration):
            events.append(("count", get_ident(), channels, duration))
            return {channel: channel for channel in channels}

        def disconnect(self):
            events.append(("disconnect", get_ident()))

    app = SharedMirrorMapApplication(
        backend="real",
        service_factory=lambda: FakeLabJack(events),
        idq_service_factory=lambda: IDQCountService(
            config.time_controller_address, controller_factory=Controller
        ),
        time_controller_address=config.time_controller_address,
    )
    assert app.map_acquisition(config).complete
    app.close()
    idq_events = [
        event
        for event in events
        if event[0] in {"construct", "connect", "configure", "count", "disconnect"}
    ]
    assert idq_events[0][0] == "construct"
    assert idq_events[-1][0] == "disconnect"
    assert len({event[1] for event in idq_events}) == 1
    assert idq_events[0][1] != get_ident()


def test_repeated_maps_reuse_one_idq_on_worker(config):
    events = []
    app = application(events)
    assert all(not r.connected for r in app.status().resources)
    app.map_acquisition(config)
    app.map_acquisition(replace(config, output_root=config.output_root / "two"))
    assert [e[0] for e in events].count("idq-connect") == 1
    worker_threads = {e[1] for e in events}
    assert len(worker_threads) == 1 and get_ident() not in worker_threads
    app.close()
    assert [e[0] for e in events].count("idq-close") == 1


def test_idq_busy_blocks_map_before_hardware(config):
    events = []
    app = application(events)
    resource = idq_resource_name(config.time_controller_address)
    lease = app.session.reserve("other-counter-user", (resource,))
    with pytest.raises(ResourceBusyError, match="other-counter-user"):
        app.map_acquisition(config)
    assert events == []
    status = next(r for r in app.status().resources if r.name == resource)
    assert status.owner == "other-counter-user" and not status.faulted
    lease.release()
    assert app.map_acquisition(
        replace(config, output_root=config.output_root / "retry")
    ).complete
    app.close()


@pytest.mark.parametrize("failure", ["connect", "configure", "count"])
def test_idq_failures_fault_only_idq_and_no_fallback(config, failure):
    events = []
    app = application(events, failure=failure)
    with pytest.raises(OSError, match="idq"):
        app.map_acquisition(config)
    statuses = {r.name: r for r in app.status().resources}
    idq = statuses[idq_resource_name(config.time_controller_address)]
    assert idq.faulted and not statuses["labjack"].faulted
    assert not any(e[0] == "count" for e in events) if failure != "count" else True
    app.close()


def test_manual_activity_does_not_open_idq(config):
    events = []
    app = application(events)
    app.manual_mirror.connect()
    app.manual_mirror.move(0, 0)
    app.manual_mirror.disconnect()
    assert not any(e[0].startswith("idq") for e in events)
    app.close()


def test_shared_simulation_imports_no_zmq(monkeypatch, config):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "zmq" or name.startswith("zmq."):
            raise AssertionError("zmq imported")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    app = SharedMirrorMapApplication(backend="simulation")
    synthetic = replace(config, backend="simulation")
    assert app.map_acquisition(synthetic).complete
    app.close()
