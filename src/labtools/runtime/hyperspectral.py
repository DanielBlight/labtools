"""Lazy, Qt-free composition for operation-scoped hyperspectral mirror access."""

from __future__ import annotations

from contextlib import asynccontextmanager


class SessionHyperspectralMirror:
    """Async adapter over a lease-scoped session mirror."""

    backend_identity = "real:instrument-session-mirror-v1"

    def __init__(self, lease) -> None:
        self._lease = lease

    async def move_to(self, x_v: float, y_v: float) -> None:
        self._lease.call("mirror", "move", x_v, y_v)

    async def home(self) -> None:
        self._lease.cleanup("mirror", "home")


class HyperspectralMirrorProvider:
    """Reserve the shared mirror/LabJack for one complete cube operation.

    The spectrometer remains owned by ``SpectrumService``. This provider does
    not claim a cross-service spectrometer reservation that the current session
    architecture cannot enforce.
    """

    def __init__(self, session, *, owner: str = "hyperspectral-service") -> None:
        self.session = session
        self.owner = owner

    @asynccontextmanager
    async def __call__(self):
        with self.session.reserve(self.owner, ("mirror",)) as lease:
            yield SessionHyperspectralMirror(lease)
