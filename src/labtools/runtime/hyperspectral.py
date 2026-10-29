"""Lazy, Qt-free operation-scoped hyperspectral composition."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager

from labtools.acquisition.hyperspectral import HyperspectralService


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
    """Reserve the actual shared mirror/LabJack for a complete cube operation."""

    def __init__(self, session, *, owner: str = "hyperspectral-service") -> None:
        self.session = session
        self.owner = owner

    @asynccontextmanager
    async def __call__(self):
        with self.session.reserve(self.owner, ("mirror",)) as lease:
            yield SessionHyperspectralMirror(lease)


@asynccontextmanager
async def open_hyperspectral_service(
    config,
    *,
    spectrum_service,
    mirror_factory,
    cancel_requested: Callable[[], bool] | None = None,
):
    """Own one mirror lease and one configured spectrum backend per operation.

    Validation and cancellation happen before either resource opens. The mirror
    context is entered first, so reservation conflicts cannot create HORIBA.
    The actual real HORIBA backend is then exclusively owned by
    ``SpectrumService.operation`` until this context exits.
    """
    config.validate()
    if cancel_requested is not None and cancel_requested():
        raise RuntimeError("Hyperspectral operation cancelled before startup")
    async with mirror_factory() as mirror, spectrum_service.operation(
        config.spectrum, cancel_requested=cancel_requested
    ) as operation_spectra:

        @asynccontextmanager
        async def borrowed_mirror():
            yield mirror

        yield HyperspectralService(operation_spectra, borrowed_mirror)
