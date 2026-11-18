"""Workspace leases backed by the existing InstrumentSession, not a new registry."""

from labtools.runtime.session import InstrumentSession


def _reservation_only():
    raise RuntimeError("Simulation workspace resources are reservation-only; no device calls")


class WorkspaceOwnership:
    """Serialize the two workflows on an explicit logical optical-path resource.

    No native handles or worker calls are routed through this session. Existing
    acquisition workers retain their thread/async-loop ownership.
    """

    def __init__(self):
        self.session = InstrumentSession({"simulation-optical-path": _reservation_only})

    def reserve(self, owner):
        return self.session.reserve(owner, ("simulation-optical-path",))

    def status(self):
        return self.session.status()

    def close(self):
        self.session.close()
