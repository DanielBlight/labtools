"""Workspace leases backed by the existing InstrumentSession, not a new registry."""

from labtools.config.workspace import WorkspaceConfig
from labtools.runtime.session import InstrumentSession


def _reservation_only():
    raise RuntimeError("Simulation workspace resources are reservation-only; no device calls")


class WorkspaceOwnership:
    """Serialize the two workflows on an explicit logical optical-path resource.

    No native handles or worker calls are routed through this session. Existing
    acquisition workers retain their thread/async-loop ownership.
    """

    def __init__(self, config=None):
        self.config = config if config is not None else WorkspaceConfig()
        self.config.validate()
        self.session = InstrumentSession({name: _reservation_only for name in self.config.resources})

    def reserve(self, owner):
        return self.session.reserve(owner, self.config.for_workflow(owner))

    def status(self):
        return self.session.status()

    def close(self):
        self.session.close()
