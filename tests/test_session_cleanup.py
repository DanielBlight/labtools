"""Restricted cleanup must not weaken normal fault exclusion."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from labtools.runtime.session import InstrumentSession, ResourceBusyError


@pytest.mark.parametrize("method", ["move", "open_gate", "close", "connect", "_hidden"])
def test_cleanup_rejects_non_allowlisted_methods(method):
    with InstrumentSession({"a": object}, cleanup_methods={"a": ("home",)}) as session:
        with session.reserve("map", ["a"]) as lease:
            with pytest.raises((PermissionError, ValueError)):
                lease.cleanup("a", method)


def test_cleanup_never_connects_or_reconnects():
    calls = []

    def factory():
        calls.append("connect")
        raise OSError("connect failed")

    with InstrumentSession({"a": factory}, cleanup_methods={"a": ("home",)}) as session:
        with session.reserve("map", ["a"]) as lease:
            with pytest.raises(RuntimeError, match="already-open"):
                lease.cleanup("a", "home")
            assert calls == []
            # An unopened resource is not faulted by an unavailable cleanup.
            with pytest.raises(OSError, match="connect failed"):
                lease.call("a", "move")
    assert calls == ["connect"]


def test_cleanup_after_factory_failure_does_not_retry_factory():
    calls = []

    def factory():
        calls.append("connect")
        raise OSError("connect failed")

    with InstrumentSession({"a": factory}, cleanup_methods={"a": ("home",)}) as session:
        with session.reserve("map", ["a"]) as lease:
            with pytest.raises(OSError):
                lease.call("a", "move")
            with pytest.raises(RuntimeError, match="already-open"):
                lease.cleanup("a", "home")
    assert calls == ["connect"]


def test_cleanup_failure_does_not_block_next_cleanup_or_clear_fault():
    calls = []

    class Device:
        def move(self):
            raise OSError("move failed")

        def home(self):
            calls.append("home")
            raise OSError("home failed")

        def close_gate(self):
            calls.append("gate close")

        def close(self):
            calls.append("disconnect")

    with InstrumentSession(
        {"a": Device}, cleanup_methods={"a": ("home", "close_gate")}
    ) as session:
        with session.reserve("map", ["a"]) as lease:
            with pytest.raises(OSError):
                lease.call("a", "move")
            with pytest.raises(OSError):
                lease.cleanup("a", "home")
            lease.cleanup("a", "close_gate")
            with pytest.raises(RuntimeError, match="faulted"):
                lease.call("a", "move")
        with pytest.raises(RuntimeError, match="faulted"):
            session.reserve("manual", ["a"])
    assert calls == ["home", "gate close", "disconnect"]


def test_cleanup_requires_active_ownership():
    with InstrumentSession(
        {"a": object, "b": object}, cleanup_methods={"a": ("home",), "b": ("home",)}
    ) as session:
        lease = session.reserve("map", ["a"])
        with pytest.raises(PermissionError):
            lease.cleanup("b", "home")
        lease.release()
        with pytest.raises(RuntimeError, match="no longer active"):
            lease.cleanup("a", "home")


@pytest.mark.parametrize(
    "allowlist",
    [{"a": "home"}, {"missing": ("home",)}, {"a": ("close",)}, {"a": ("_x",)}],
)
def test_invalid_allowlist(allowlist):
    with pytest.raises(ValueError):
        InstrumentSession({"a": object}, cleanup_methods=allowlist)


def test_cleanup_inflight_prevents_release():
    entered, finish = Event(), Event()

    class Device:
        def ping(self):
            pass

        def home(self):
            entered.set()
            assert finish.wait(4)

        def close(self):
            pass

    with InstrumentSession({"a": Device}, cleanup_methods={"a": ("home",)}) as session:
        with session.reserve("map", ["a"]) as lease:
            lease.call("a", "ping")
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(lease.cleanup, "a", "home")
                try:
                    assert entered.wait(3)
                    with pytest.raises(ResourceBusyError):
                        lease.release()
                finally:
                    finish.set()
                future.result(timeout=3)


def test_cleanup_accepts_no_user_arguments():
    with InstrumentSession({"a": object}, cleanup_methods={"a": ("home",)}) as session:
        with session.reserve("map", ["a"]) as lease:
            with pytest.raises(TypeError):
                lease.cleanup("a", "home", 123)


def test_queued_cleanup_runs_after_fault_but_queued_normal_command_does_not():
    import time

    entered, finish = Event(), Event()
    calls = []

    class Device:
        def fail(self):
            entered.set()
            assert finish.wait(5)
            raise OSError("move failed")

        def move(self):
            calls.append("forbidden move")

        def close_gate(self):
            calls.append("gate close")

        def close(self):
            pass

    with InstrumentSession(
        {"a": Device}, cleanup_methods={"a": ("close_gate",)}
    ) as session, session.reserve("map", ["a"]) as lease:
        with ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(lease.call, "a", "fail")
            try:
                assert entered.wait(3)
                second = pool.submit(lease.call, "a", "move")
                third = pool.submit(lease.cleanup, "a", "close_gate")
                deadline = time.monotonic() + 3
                while True:
                    with session._lock:
                        if session._leases[lease._token][2] == 3:
                            break
                    assert time.monotonic() < deadline
                    time.sleep(0.001)
            finally:
                finish.set()
            with pytest.raises(OSError):
                first.result(timeout=3)
            with pytest.raises(RuntimeError, match="faulted"):
                second.result(timeout=3)
            third.result(timeout=3)
        assert calls == ["gate close"]
