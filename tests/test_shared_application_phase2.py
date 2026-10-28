"""Phase 2 composition tests with fake LabJack services only."""

from threading import get_ident

import pytest

from labtools.runtime.session import ResourceBusyError
from labtools.runtime.shared_application import (
    SharedMirrorMapApplication,
)


class FakeLabJackService:
    def __init__(self, calls):
        self.calls = calls
        calls.append(("connect", get_ident()))

    def move(self, x, y):
        self.calls.append(("move", get_ident(), x, y))

    def home(self):
        self.calls.append(("home", get_ident()))

    def open_gate(self):
        self.calls.append(("gate open", get_ident()))

    def close_gate(self):
        self.calls.append(("gate close", get_ident()))

    def close(self):
        self.calls.append(("close", get_ident()))


def application():
    calls = []
    app = SharedMirrorMapApplication(
        service_factory=lambda: FakeLabJackService(calls),
        backend="real",
    )
    return app, calls


def resource(status):
    return status.resources[0]


def test_manual_is_lazy_reuses_one_connection_and_close_once():
    app, calls = application()
    assert resource(app.status()).state == "available"
    assert not resource(app.status()).connected
    app.manual_mirror.connect()
    assert resource(app.status()).state == "busy"
    assert resource(app.status()).owner == "manual-mirror"
    assert not resource(app.status()).connected
    app.manual_mirror.move(1.0, -2.0)
    assert resource(app.status()).connected
    app.manual_mirror.disconnect()
    app.manual_mirror.connect()
    app.manual_mirror.move(0.5, 0.25)
    app.manual_mirror.disconnect()
    app.close()
    assert [x[0] for x in calls] == ["connect", "move", "move", "close"]
    worker_threads = {x[1] for x in calls}
    assert len(worker_threads) == 1
    assert get_ident() not in worker_threads


def test_manual_conflict_is_recoverable_and_does_not_fault():
    app, calls = application()
    lease = app.session.reserve("intensity-map", ("mirror", "gate"))
    with pytest.raises(ResourceBusyError):
        app.manual_mirror.connect()
    status = resource(app.status())
    assert status.state == "busy" and status.owner == "intensity-map"
    assert not status.faulted and calls == []
    lease.release()
    app.manual_mirror.connect()
    app.manual_mirror.disconnect()
    app.close()


def test_shutdown_refuses_active_manual_lease_without_disconnect_or_home():
    app, calls = application()
    app.manual_mirror.connect()
    with pytest.raises(ResourceBusyError):
        app.close()
    assert calls == []
    app.manual_mirror.disconnect()
    app.close()
    assert calls == []


def test_device_failure_faults_status_and_blocks_normal_reuse():
    calls = []

    class Failing(FakeLabJackService):
        def move(self, x, y):
            super().move(x, y)
            raise OSError("injected move failure")

    app = SharedMirrorMapApplication(
        service_factory=lambda: Failing(calls), backend="real"
    )
    app.manual_mirror.connect()
    with pytest.raises(OSError):
        app.manual_mirror.move(1, 1)
    status = resource(app.status())
    assert status.state == "faulted" and status.faulted
    app.manual_mirror.disconnect()
    with pytest.raises(RuntimeError, match="faulted"):
        app.manual_mirror.connect()
    app.close()
