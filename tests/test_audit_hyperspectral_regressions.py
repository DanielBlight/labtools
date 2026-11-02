"""Offline regressions for the fresh-snapshot source audit."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

import labtools.measurements.hyperspectral as facade
from labtools.config.hyperspectral import HyperspectralConfig
from labtools.config.spectrum import SpectrumSettings


def request():
    settings = SpectrumSettings(
        "audit-spectrum", "syncerity", 0.1, 2, 0, 0.5, 500, 600,
        backend="simulation",
    )
    return facade.HyperspectralRequest(
        HyperspectralConfig("audit-cube", settings, 0, 1, 2, 0, 1, 2)
    )


class FakeRuntime:
    def __init__(self, *, check_error=None, close_error=None):
        self.check_error = check_error
        self.close_error = close_error
        self.closed = 0
        self.spectrum_service = object()
        self.mirror_factory = object()

    def check(self, config):
        if self.check_error is not None:
            raise self.check_error

    def close(self):
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


@pytest.mark.parametrize("error", [ValueError("invalid runtime"), asyncio.CancelledError()])
def test_owned_runtime_check_failure_closes(monkeypatch, error):
    runtime = FakeRuntime(check_error=error)
    monkeypatch.setattr(facade, "HyperspectralRuntime", lambda **kwargs: runtime)
    with pytest.raises(type(error)) as caught:
        asyncio.run(facade.acquire_hyperspectral_map_async(request()))
    assert caught.value is error
    assert runtime.closed == 1


@pytest.mark.parametrize("primary", [RuntimeError("acquisition"), asyncio.CancelledError()])
@pytest.mark.parametrize("cleanup", [RuntimeError("cleanup"), KeyboardInterrupt("cleanup")])
def test_primary_failure_survives_owned_cleanup(monkeypatch, primary, cleanup):
    runtime = FakeRuntime(close_error=cleanup)
    monkeypatch.setattr(facade, "HyperspectralRuntime", lambda **kwargs: runtime)

    @asynccontextmanager
    async def opening(*args, **kwargs):
        raise primary
        yield  # pragma: no cover - async context-manager protocol

    monkeypatch.setattr(facade, "open_hyperspectral_service", opening)
    with pytest.raises(type(primary)) as caught:
        asyncio.run(facade.acquire_hyperspectral_map_async(request()))
    assert caught.value is primary
    assert runtime.closed == 1
    assert any("cleanup failed" in note for note in primary.__notes__)


def test_borrowed_runtime_is_not_closed_after_validation_failure():
    error = ValueError("invalid borrowed runtime")
    runtime = FakeRuntime(check_error=error)
    with pytest.raises(ValueError) as caught:
        asyncio.run(facade.acquire_hyperspectral_map_async(request(), runtime=runtime))
    assert caught.value is error
    assert runtime.closed == 0


def test_cleanup_failure_after_success_is_not_hidden(monkeypatch):
    error = RuntimeError("cleanup after success")
    runtime = FakeRuntime(close_error=error)
    monkeypatch.setattr(facade, "HyperspectralRuntime", lambda **kwargs: runtime)

    class Service:
        async def acquire(self, *args, **kwargs):
            return object()

    @asynccontextmanager
    async def opening(*args, **kwargs):
        yield Service()

    monkeypatch.setattr(facade, "open_hyperspectral_service", opening)
    monkeypatch.setattr(facade, "_wrap", lambda value: value)
    with pytest.raises(RuntimeError) as caught:
        asyncio.run(facade.acquire_hyperspectral_map_async(request()))
    assert caught.value is error
    assert runtime.closed == 1
