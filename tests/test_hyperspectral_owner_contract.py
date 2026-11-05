"""Characterize owner labels without changing acquisition or reservation behavior."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

import labtools.measurements.hyperspectral as facade
from labtools.config.hyperspectral import HyperspectralConfig
from labtools.config.spectrum import SpectrumSettings
from labtools.measurements.recipes import MeasurementRecipe, load_recipe, save_recipe
from labtools.runtime.hyperspectral import (
    HyperspectralMirrorProvider,
    open_hyperspectral_service,
)
from labtools.runtime.session import InstrumentSession, ResourceBusyError


def config():
    settings = SpectrumSettings(
        "owner-contract-spectrum-v1", "syncerity", 0.1, 2, 0, 0.5,
        500.0, 600.0, backend="real",
    )
    return HyperspectralConfig(
        "owner-contract-v1", settings, 0.0, 0.1, 2, 0.0, 0.1, 2,
        backend="real",
    )


@pytest.fixture
def session():
    def forbidden_open():
        raise AssertionError("Label characterization must not open a device")

    with InstrumentSession(
        {"labjack": forbidden_open}, aliases={"mirror": "labjack", "gate": "labjack"}
    ) as value:
        yield value


@pytest.mark.parametrize("owner", ["scripted-hyperspectral", "custom-request", " padded "])
def test_request_and_recipe_preserve_label(owner, tmp_path):
    request = facade.HyperspectralRequest(config(), owner=owner)
    request.validate()
    recipe = MeasurementRecipe("hyperspectral", request)
    path = tmp_path / "recipe.json"
    save_recipe(path, recipe)
    restored = load_recipe(path)
    assert restored.request.owner == owner
    assert facade.HyperspectralRequest(config()).owner == "scripted-hyperspectral"


@pytest.mark.parametrize("owner", ["", "   "])
def test_blank_request_owner_still_rejected(owner):
    with pytest.raises(ValueError, match="owner must be nonempty"):
        facade.HyperspectralRequest(config(), owner=owner).validate()


@pytest.mark.parametrize("owner", ["hyperspectral-service", "custom-provider"])
def test_provider_label_is_diagnostic_and_released(session, owner):
    provider = HyperspectralMirrorProvider(session, owner=owner)

    async def exercise():
        async with provider():
            assert session.reservations() == {"labjack": owner}
        assert session.reservations() == {}

    asyncio.run(exercise())
    assert HyperspectralMirrorProvider(session).owner == "hyperspectral-service"


@pytest.mark.parametrize("contender", ["hyperspectral-service", "other-label"])
@pytest.mark.parametrize("alias", ["mirror", "gate", "labjack"])
def test_conflict_depends_on_physical_resource_not_label(session, contender, alias):
    provider = HyperspectralMirrorProvider(session)

    async def exercise():
        async with provider():
            with pytest.raises(ResourceBusyError):
                session.reserve(contender, (alias,))
        with session.reserve(contender, (alias,)):
            assert session.reservations() == {"labjack": contender}

    asyncio.run(exercise())


@pytest.mark.parametrize("error", [RuntimeError("failure"), asyncio.CancelledError("cancel")])
def test_provider_releases_on_exception_preserving_identity(session, error):
    provider = HyperspectralMirrorProvider(session)

    async def exercise():
        with pytest.raises(type(error)) as caught:
            async with provider():
                raise error
        assert caught.value is error
        assert session.reservations() == {}
        with session.reserve("next", ("mirror",)):
            pass

    asyncio.run(exercise())


@pytest.mark.parametrize("owner", ["scripted-hyperspectral", "custom-request"])
@pytest.mark.parametrize("owned", [False, True])
@pytest.mark.parametrize("provider_owner", [None, "explicit-provider"])
def test_facade_does_not_propagate_request_label(
    monkeypatch, session, owner, owned, provider_owner,
):
    composition = (
        {"session": session} if provider_owner is None else
        {"mirror_factory": HyperspectralMirrorProvider(session, owner=provider_owner)}
    )
    expected_label = provider_owner or "hyperspectral-service"
    runtime = facade.HyperspectralRuntime(
        backend="real", spectrum_service=object(), **composition,
    )
    provider = runtime.mirror_factory
    assert isinstance(provider, HyperspectralMirrorProvider)
    sentinel = object()
    seen = []

    class Service:
        async def acquire(self, *args, **kwargs):
            seen.append(session.reservations())
            return sentinel

    @asynccontextmanager
    async def fake_open(config, *, spectrum_service, mirror_factory, cancel_requested):
        assert mirror_factory is provider
        async with mirror_factory():
            yield Service()

    monkeypatch.setattr(facade, "open_hyperspectral_service", fake_open)
    monkeypatch.setattr(facade, "_wrap", lambda result: result)
    if owned:
        def factory(*, backend):
            assert backend == "real"
            return runtime
        monkeypatch.setattr(facade, "HyperspectralRuntime", factory)
    try:
        result = asyncio.run(facade.acquire_hyperspectral_map_async(
            facade.HyperspectralRequest(config(), owner=owner),
            runtime=None if owned else runtime,
        ))
        assert result is sentinel
        assert seen == [{"labjack": expected_label}]
        assert provider.owner == expected_label
        assert session.reservations() == {}
        assert runtime._closed is owned
        with session.reserve("still-borrowed-session", ("mirror",)):
            pass
    finally:
        runtime.close()


@pytest.mark.parametrize("failure", [False, True])
def test_custom_factory_is_retained_called_without_arguments_and_unwound(session, failure):
    events = []
    error = RuntimeError("injected body failure")
    mirror = object()

    @asynccontextmanager
    async def custom_factory():
        events.append("mirror-enter")
        with session.reserve("custom-provider", ("mirror",)):
            try:
                yield mirror
            finally:
                events.append("mirror-exit")

    class Spectra:
        closed = False

        @asynccontextmanager
        async def operation(self, settings, *, cancel_requested):
            assert session.reservations() == {"labjack": "custom-provider"}
            events.append("spectrum-enter")
            try:
                yield self
            finally:
                events.append("spectrum-exit")

        def close(self):
            self.closed = True

    spectra = Spectra()
    runtime = facade.HyperspectralRuntime(
        backend="real", spectrum_service=spectra, mirror_factory=custom_factory,
    )
    assert runtime.mirror_factory is custom_factory

    async def exercise():
        async with open_hyperspectral_service(
            config(), spectrum_service=spectra, mirror_factory=runtime.mirror_factory,
        ):
            assert session.reservations() == {"labjack": "custom-provider"}
            if failure:
                raise error

    try:
        if failure:
            with pytest.raises(RuntimeError) as caught:
                asyncio.run(exercise())
            assert caught.value is error
        else:
            asyncio.run(exercise())
        assert session.reservations() == {}
        assert events == ["mirror-enter", "spectrum-enter", "spectrum-exit", "mirror-exit"]
        assert not spectra.closed
    finally:
        runtime.close()
    assert not spectra.closed


def test_task_cancellation_releases_provider_reservation(session):
    provider = HyperspectralMirrorProvider(session)

    async def exercise():
        entered = asyncio.Event()

        async def operation():
            async with provider():
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(operation())
        try:
            await asyncio.wait_for(entered.wait(), timeout=2.0)
            assert session.reservations() == {"labjack": "hyperspectral-service"}
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2.0)
            assert session.reservations() == {}
            with session.reserve("after-cancel", ("mirror",)):
                pass
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    asyncio.run(exercise())
