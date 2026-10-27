"""Session foundation tests: injected fake devices only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, get_ident
import pytest
from labtools.runtime.session import InstrumentSession, ResourceBusyError, SessionClosedError


def setup_session(*, fail=False, close_fail=False):
    calls = []
    class Device:
        def move(self, x, y):
            calls.append(("move", get_ident(), x, y))
            if fail:
                raise OSError("injected move failure")
            return x, y
        def close(self):
            calls.append(("close", get_ident()))
            if close_fail:
                raise OSError("injected close failure")
    def factory():
        calls.append(("connect", get_ident()))
        return Device()
    session = InstrumentSession({"labjack": factory}, aliases={"mirror": "labjack", "gate": "labjack"})
    return session, calls


def test_lazy_connection_and_reuse():
    s, calls = setup_session()
    with s:
        assert calls == []
        with s.reserve("manual", ["mirror"]) as lease:
            assert lease.call("mirror", "move", 1, 2) == (1, 2)
        with s.reserve("map", ["mirror", "gate"]) as lease:
            lease.call("mirror", "move", 3, 4)
        assert [c[0] for c in calls] == ["connect", "move", "move"]
    assert [c[0] for c in calls] == ["connect", "move", "move", "close"]
    assert len({c[1] for c in calls}) == 1
    assert calls[0][1] != get_ident()


@pytest.mark.parametrize("alias", ["mirror", "gate", "labjack"])
def test_alias_conflict_even_with_same_owner(alias):
    s, calls = setup_session()
    with s:
        with s.reserve("same-label", ["mirror"]):
            with pytest.raises(ResourceBusyError):
                s.reserve("same-label", [alias])
        assert calls == []


def test_atomic_multi_resource_reservation():
    with InstrumentSession({"a": object, "b": object}) as s:
        with s.reserve("one", ["b"]):
            with pytest.raises(ResourceBusyError):
                s.reserve("two", ["a", "b"])
            with s.reserve("three", ["a"]):
                assert s.reservations() == {"a": "three", "b": "one"}


def test_release_on_measurement_failure():
    s, _ = setup_session()
    with s:
        with pytest.raises(ValueError):
            with s.reserve("map", ["mirror"]):
                raise ValueError("measurement")
        with s.reserve("manual", ["mirror"]):
            pass


def test_stale_lease_and_idempotent_release():
    s, _ = setup_session()
    with s:
        lease = s.reserve("map", ["mirror"])
        lease.release()
        lease.release()
        with pytest.raises(RuntimeError, match="no longer active"):
            lease.call("mirror", "move", 1, 2)


def test_unreserved_resource_rejected():
    with InstrumentSession({"a": object, "b": object}) as s:
        with s.reserve("one", ["a"]) as lease:
            with pytest.raises(PermissionError):
                lease.call("b", "move")


@pytest.mark.parametrize("method", ["close", "connect", "disconnect", "_private"])
def test_lifecycle_calls_rejected(method):
    s, calls = setup_session()
    with s:
        with s.reserve("manual", ["mirror"]) as lease:
            with pytest.raises(ValueError):
                lease.call("mirror", method)
    assert calls == []


def test_shutdown_refuses_active_measurement():
    s, _ = setup_session()
    with s.reserve("map", ["mirror"]):
        with pytest.raises(ResourceBusyError):
            s.close()
    s.close()
    s.close()
    with pytest.raises(SessionClosedError):
        s.reserve("manual", ["mirror"])


def test_command_failure_faults_resource_and_still_closes():
    s, calls = setup_session(fail=True)
    with s:
        with s.reserve("map", ["mirror"]) as lease:
            with pytest.raises(OSError):
                lease.call("mirror", "move", 1, 2)
            with pytest.raises(RuntimeError, match="faulted"):
                lease.call("mirror", "move", 1, 2)
        with pytest.raises(RuntimeError, match="faulted"):
            s.reserve("manual", ["mirror"])
    assert calls[-1][0] == "close"


def test_independent_shutdown_and_primary_preserved():
    calls = []
    class Device:
        def ping(self): return None
        def close(self):
            calls.append("close")
            raise OSError("close failed")
    s = InstrumentSession({"a": Device, "b": Device})
    with pytest.raises(ExceptionGroup) as caught:
        with s:
            with s.reserve("map", ["a", "b"]) as lease:
                lease.call("a", "ping")
                lease.call("b", "ping")
    assert len(caught.value.exceptions) == 2
    assert calls == ["close", "close"]
    s, _ = setup_session(close_fail=True)
    with pytest.raises(ValueError) as caught:
        with s:
            with s.reserve("map", ["mirror"]) as lease:
                lease.call("mirror", "move", 1, 2)
            raise ValueError("primary")
    assert "shutdown failed" in caught.value.__notes__[0]


def test_inflight_lease_cannot_release_or_shutdown():
    entered, release = Event(), Event()
    class Device:
        def block(self):
            entered.set()
            assert release.wait(5)
        def close(self): pass
    with InstrumentSession({"labjack": Device}) as s:
        lease = s.reserve("map", ["labjack"])
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lease.call, "labjack", "block")
            try:
                assert entered.wait(3)
                with pytest.raises(ResourceBusyError): lease.release()
                with pytest.raises(ResourceBusyError): s.close()
                with pytest.raises(ResourceBusyError): s.reserve("manual", ["labjack"])
            finally:
                release.set()
            future.result(timeout=3)
        lease.release()


def test_concurrent_reservation_has_single_winner():
    s, _ = setup_session()
    with s:
        def attempt(i):
            try: return s.reserve(str(i), ["mirror"])
            except ResourceBusyError: return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(32)))
        winners = [r for r in results if r is not None]
        assert len(winners) == 1
        winners[0].release()


def test_factory_failure_releases_lease_without_fallback():
    def fail(): raise OSError("factory")
    with InstrumentSession({"a": fail}) as s:
        with pytest.raises(OSError):
            with s.reserve("map", ["a"]) as lease:
                lease.call("a", "ping")
        assert s.reservations() == {}


@pytest.mark.parametrize("resources", [[], ["unknown"], "mirror"])
def test_invalid_reservations(resources):
    s, _ = setup_session()
    with s:
        with pytest.raises(ValueError): s.reserve("manual", resources)


def test_recursive_worker_call_rejected_without_deadlock():
    class Device:
        def recurse(self): return lease.call("a", "recurse")
        def close(self): pass
    with InstrumentSession({"a": Device}) as s:
        with s.reserve("map", ["a"]) as lease:
            with pytest.raises(RuntimeError, match="Recursive"):
                lease.call("a", "recurse")


def test_queued_command_does_not_run_after_prior_failure():
    import time
    entered, release = Event(), Event()
    calls = []
    class Device:
        def fail(self):
            entered.set()
            assert release.wait(5)
            raise OSError("first command")
        def move(self): calls.append("must not run")
        def close(self): pass
    with InstrumentSession({"a": Device}) as s:
        with s.reserve("map", ["a"]) as lease:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(lease.call, "a", "fail")
                try:
                    assert entered.wait(3)
                    second = pool.submit(lease.call, "a", "move")
                    deadline = time.monotonic() + 3
                    while True:
                        with s._lock:
                            queued = s._leases[lease._token][2] == 2
                        if queued: break
                        assert time.monotonic() < deadline
                        time.sleep(.001)
                finally:
                    release.set()
                with pytest.raises(OSError): first.result(timeout=3)
                with pytest.raises(RuntimeError, match="faulted"): second.result(timeout=3)
            assert calls == []


def test_import_has_no_native_dependencies(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    code = """
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('labtools.devices', 'PyQt6', 'horiba_sdk', 'u6', 'serial')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from labtools.runtime.session import InstrumentSession
with InstrumentSession({'a': object}):
    pass
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', code], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
