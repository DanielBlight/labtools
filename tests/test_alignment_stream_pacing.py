"""Qt-free stream pacing tests; no physical devices or driver imports."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.acquisition.spectrum_service import SpectrumService


def test_simulation_waits_and_stop_during_wait_prevents_next_capture(monkeypatch):
    async def run():
        events = []
        delays = []
        stopped = False
        original_sleep = asyncio.sleep

        @asynccontextmanager
        async def factory(settings):
            events.append("open")

            class Backend:
                actual_centre_nm = 690.0

                async def capture(self, subtract_dark):
                    events.append("capture")
                    return [690.0], [4.0], [5.0]

            try:
                yield Backend()
            finally:
                events.append("close")

        async def sleep(delay):
            nonlocal stopped
            delays.append(delay)
            stopped = True
            await original_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", sleep)
        service = SpectrumService(lambda s: None, factory)
        with pytest.raises(asyncio.CancelledError):
            await service.run_alignment(
                AlignmentSettings("test", backend="simulation", exposure_s=1000.0),
                publish_frame=lambda frame: events.append("publish"),
                cancel_requested=lambda: stopped,
            )
        assert events == ["open", "capture", "publish", "close"]
        assert len(delays) == 1
        assert 0 < delays[0] <= 0.05

    asyncio.run(run())


def test_real_stream_does_not_add_positive_delay(monkeypatch):
    async def run():
        frames = []
        delays = []
        original_sleep = asyncio.sleep

        @asynccontextmanager
        async def factory(settings):
            class Backend:
                actual_centre_nm = 690.0

                async def capture(self, subtract_dark):
                    return [690.0], [4.0], [5.0]

            yield Backend()

        async def sleep(delay):
            delays.append(delay)
            await original_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", sleep)
        service = SpectrumService(lambda s: None, factory)
        with pytest.raises(asyncio.CancelledError):
            await service.run_alignment(
                AlignmentSettings("test", backend="real"),
                publish_frame=frames.append,
                cancel_requested=lambda: len(frames) >= 3,
            )
        assert len(frames) == 3
        assert delays and all(delay == 0 for delay in delays)

    asyncio.run(run())


def test_stop_from_frame_publication_skips_simulated_wait(monkeypatch):
    async def run():
        stopped = False
        closed = []

        @asynccontextmanager
        async def factory(settings):
            class Backend:
                actual_centre_nm = 690.0

                async def capture(self, subtract_dark):
                    return [690.0], [4.0], [5.0]

            try:
                yield Backend()
            finally:
                closed.append(True)

        async def unexpected_sleep(delay):
            pytest.fail("Stop should be observed before the pacing wait")

        def publish(frame):
            nonlocal stopped
            stopped = True

        monkeypatch.setattr(asyncio, "sleep", unexpected_sleep)
        service = SpectrumService(lambda s: None, factory)
        with pytest.raises(asyncio.CancelledError):
            await service.run_alignment(
                AlignmentSettings("test", backend="simulation"),
                publish_frame=publish,
                cancel_requested=lambda: stopped,
            )
        assert closed == [True]

    asyncio.run(run())


def test_one_shot_simulation_is_not_paced(monkeypatch):
    from labtools.runtime.spectrum_backend import create_spectrum_service

    async def run():
        async def unexpected_sleep(delay):
            pytest.fail("One-shot API must not inherit continuous-display pacing")

        monkeypatch.setattr(asyncio, "sleep", unexpected_sleep)
        result = await create_spectrum_service(backend="simulation").acquire_alignment(
            AlignmentSettings("test", backend="simulation")
        )
        assert result.settings.backend == "simulation"
        assert len(result.intensity) == 64

    asyncio.run(run())
