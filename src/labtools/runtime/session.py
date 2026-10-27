"""Opt-in, process-local sessions. No native imports or automatic connections.

Factories, device methods and close() run on one persistent worker thread.
This is not an interlock, cross-process lock or blocked-driver timeout.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import RLock, get_ident
from uuid import uuid4


class ResourceBusyError(RuntimeError):
    """A measurement already owns a requested physical resource."""


class SessionClosedError(RuntimeError):
    """The session is closing or closed."""


class Reservation:
    """A whole-measurement lease; owner labels do not confer authority."""

    def __init__(self, session, token, resources):
        self._session = session
        self._token = token
        self.resources = resources

    def call(self, resource, method, *args, **kwargs):
        return self._session._call(self._token, resource, method, args, kwargs)

    def release(self):
        self._session._release(self._token)

    def __enter__(self):
        self._session._validate(self._token)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.release()
        except Exception as cleanup:
            if exc is None:
                raise
            exc.add_note(f"Reservation release failed: {cleanup!r}")


class InstrumentSession:
    """Own explicitly injected resources until explicit session shutdown.

    Example aliases: mirror -> labjack, gate -> labjack. An injected LabJack
    service must expose the reviewed mirror/gate operations; raw wrappers are
    not adapted here. Existing standalone GUIs do not use this class yet.
    """

    def __init__(self, factories, *, aliases=None):
        self._factories = dict(factories)
        if not self._factories or any(
            not isinstance(k, str) or not k.strip() or not callable(v)
            for k, v in self._factories.items()
        ):
            raise ValueError("Provide named callable resource factories")
        self._aliases = dict(aliases or {})
        if any(
            not isinstance(k, str) or not k.strip()
            or k in self._factories or v not in self._factories
            for k, v in self._aliases.items()
        ):
            raise ValueError("Aliases must map new names directly to physical resources")
        self._lock = RLock()
        self._leases = {}
        self._owners = {}
        self._devices = {}
        self._faults = set()
        self._state = "open"
        self._worker_ident = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="labtools-session")

    def _physical(self, name):
        physical = self._aliases.get(name, name)
        if physical not in self._factories:
            raise ValueError(f"Unknown resource: {name!r}")
        return physical

    def _open(self):
        if self._state != "open":
            raise SessionClosedError(f"Session is {self._state}")

    def reserve(self, owner, resources):
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("Provide a nonempty owner label")
        if isinstance(resources, str):
            raise ValueError("Pass a sequence of resource names, not a string")
        physical = frozenset(self._physical(name) for name in resources)
        if not physical:
            raise ValueError("Reserve at least one resource")
        with self._lock:
            self._open()
            conflicts = physical.intersection(self._owners)
            if conflicts:
                raise ResourceBusyError(f"Resources already reserved: {sorted(conflicts)}")
            if physical.intersection(self._faults):
                raise RuntimeError("Resource faulted; close the session before reconnecting")
            token = uuid4().hex
            self._leases[token] = [physical, owner, 0]
            for name in physical:
                self._owners[name] = token
            return Reservation(self, token, physical)

    def _validate(self, token):
        with self._lock:
            self._open()
            if token not in self._leases:
                raise RuntimeError("Reservation is no longer active")

    def _release(self, token):
        with self._lock:
            lease = self._leases.get(token)
            if lease is None:
                return
            if lease[2]:
                raise ResourceBusyError("Cannot release a reservation with commands in flight")
            for name in lease[0]:
                del self._owners[name]
            del self._leases[token]

    def _execute(self, physical, method, args, kwargs):
        self._worker_ident = get_ident()
        if physical not in self._devices:
            # Factories must clean up their own partially constructed resources.
            device = self._factories[physical]()
            if not callable(getattr(device, "close", None)):
                raise TypeError("Session resource must provide close()")
            self._devices[physical] = device
        return getattr(self._devices[physical], method)(*args, **kwargs)

    def _call(self, token, resource, method, args, kwargs):
        if get_ident() == self._worker_ident:
            raise RuntimeError("Recursive session calls from the worker are forbidden")
        if not isinstance(method, str) or method.startswith("_") or method in {"close", "connect", "disconnect"}:
            raise ValueError("Lifecycle and private methods are session-owned")
        physical = self._physical(resource)
        with self._lock:
            self._validate(token)
            lease = self._leases[token]
            if physical not in lease[0]:
                raise PermissionError("Resource is not covered by this reservation")
            if physical in self._faults:
                raise RuntimeError("Resource faulted; further commands are blocked")
            lease[2] += 1
            def execute():
                try:
                    with self._lock:
                        if physical in self._faults:
                            raise RuntimeError("Resource faulted before queued command ran")
                    return self._execute(physical, method, args, kwargs)
                except BaseException:
                    with self._lock:
                        self._faults.add(physical)
                    raise
                finally:
                    with self._lock:
                        lease[2] -= 1
            try:
                future = self._executor.submit(execute)
            except BaseException:
                lease[2] -= 1
                raise
        # A caller interruption does not release an executing command's lease.
        return future.result()

    def reservations(self):
        """Return a detached diagnostic snapshot, never raw device handles."""
        with self._lock:
            return {name: self._leases[token][1] for name, token in self._owners.items()}

    def _close_devices(self):
        self._worker_ident = get_ident()
        failures = []
        for name, device in reversed(list(self._devices.items())):
            try:
                device.close()
            except Exception as exc:
                exc.add_note(f"Session resource: {name}")
                failures.append(exc)
        self._devices.clear()
        if failures:
            raise ExceptionGroup("Session shutdown failed; physical state may be unknown", failures)

    def close(self):
        if get_ident() == self._worker_ident:
            raise RuntimeError("Cannot close the session from its worker")
        with self._lock:
            if self._state == "closed":
                return
            self._open()
            if self._leases:
                raise ResourceBusyError("Release all measurements before closing the session")
            self._state = "closing"
            future = self._executor.submit(self._close_devices)
        try:
            future.result()
        finally:
            self._executor.shutdown(wait=True)
            with self._lock:
                self._state = "closed"

    def __enter__(self):
        with self._lock:
            self._open()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.close()
        except Exception as cleanup:
            if exc is None:
                raise
            exc.add_note(f"Session shutdown failed: {cleanup!r}")
