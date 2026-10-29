from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import numpy as np
import pytest

from labtools.acquisition.hyperspectral import (
    HyperspectralAcquisitionError,
    HyperspectralService,
)
from labtools.acquisition.spectrum_service import SpectrumResult
from labtools.config.hyperspectral import HyperspectralConfig
from labtools.config.spectrum import SpectrumSettings


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def config():
    settings = SpectrumSettings(
        "failure-matrix-v1", "syncerity", 0.1, 2, 0, 0.5, 500, 600, backend="simulation"
    )
    return HyperspectralConfig("failure-matrix-v1", settings, 0, 1, 2, 0, 1, 2)


class Spectra:
    def __init__(self, fail_at=None, axis_change_at=None):
        self.calls = 0
        self.fail_at = fail_at
        self.axis_change_at = axis_change_at
        self.closed = 0

    async def acquire(self, settings, **kwargs):
        self.calls += 1
        if self.calls == self.fail_at:
            raise OSError(f"spectrum-{self.calls}")
        x = np.linspace(500, 600, 4) + (1 if self.calls == self.axis_change_at else 0)
        y = np.arange(4, dtype=float)
        return SpectrumResult(settings, x, y, y, "none", None)

    async def close(self):
        self.closed += 1


def mirrors(*, fail_move=None, exit_error=None, events=None):
    events = [] if events is None else events

    class Mirror:
        backend_identity = "simulation:failure-matrix"
        calls = 0

        async def move_to(self, x, y):
            self.calls += 1
            events.append(f"move-{self.calls}")
            if self.calls == fail_move:
                raise OSError(f"move-{self.calls}")

        async def home(self):
            events.append("home")

    @asynccontextmanager
    async def factory():
        events.append("open")
        try:
            yield Mirror()
        finally:
            events.append("exit")
            if exit_error:
                raise RuntimeError(exit_error)

    return factory


@pytest.mark.parametrize("fail_at,completed", [(1, 0), (3, 2)])
def test_spectrum_failures_return_partial(config, fail_at, completed):
    with pytest.raises(HyperspectralAcquisitionError) as caught:
        run(HyperspectralService(Spectra(fail_at=fail_at), mirrors()).acquire(config))
    assert isinstance(caught.value.__cause__, OSError)
    assert caught.value.partial_result.completed_points == completed
    assert caught.value.partial_result.status == "failed"


@pytest.mark.parametrize("fail_at,completed", [(1, 0), (3, 2)])
def test_move_failures_return_partial(config, fail_at, completed):
    with pytest.raises(HyperspectralAcquisitionError) as caught:
        run(HyperspectralService(Spectra(), mirrors(fail_move=fail_at)).acquire(config))
    assert caught.value.partial_result.completed_points == completed


def test_axis_mismatch_is_causal_failure(config):
    with pytest.raises(HyperspectralAcquisitionError) as caught:
        run(HyperspectralService(Spectra(axis_change_at=2), mirrors()).acquire(config))
    assert isinstance(caught.value.__cause__, ValueError)
    assert caught.value.partial_result.completed_points == 1


def test_cancel_after_completed_point_is_immutable(config):
    checks = 0

    def cancel():
        nonlocal checks
        checks += 1
        return checks > 1

    result = run(
        HyperspectralService(Spectra(), mirrors()).acquire(
            config, cancel_requested=cancel
        )
    )
    assert result.status == "cancelled" and result.completed_points == 1
    assert (
        not result.intensity.flags.writeable
        and not result.completed_mask.flags.writeable
    )


def test_owned_close_once_and_borrowed_never(config):
    owned, borrowed = Spectra(), Spectra()

    async def exercise():
        async with HyperspectralService(owned, mirrors(), owns_spectrum_service=True):
            pass
        async with HyperspectralService(borrowed, mirrors()):
            pass

    run(exercise())
    assert owned.closed == 1 and borrowed.closed == 0


def test_owned_close_failure_preserves_body_error(config):
    class BadClose(Spectra):
        async def close(self):
            raise RuntimeError("close-failed")

    async def exercise():
        async with HyperspectralService(
            BadClose(fail_at=1), mirrors(), owns_spectrum_service=True
        ) as service:
            await service.acquire(config)

    with pytest.raises(HyperspectralAcquisitionError) as caught:
        run(exercise())
    assert any("cleanup failed" in note for note in caught.value.__notes__)


def test_keyboard_interrupt_is_not_wrapped(config):
    class Interrupt(Spectra):
        async def acquire(self, settings, **kwargs):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(HyperspectralService(Interrupt(), mirrors()).acquire(config))


def test_mirror_context_startup_failure_is_causal(config):
    @asynccontextmanager
    async def failed_startup():
        raise ConnectionError("mirror-startup")
        yield

    with pytest.raises(HyperspectralAcquisitionError) as caught:
        run(HyperspectralService(Spectra(), failed_startup).acquire(config))
    assert isinstance(caught.value.__cause__, ConnectionError)
    assert caught.value.partial_result.completed_points == 0


def test_mirror_context_exit_failure_retains_complete_cube(config):
    with pytest.raises(HyperspectralAcquisitionError) as caught:
        run(
            HyperspectralService(Spectra(), mirrors(exit_error="mirror-exit")).acquire(
                config
            )
        )
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert caught.value.partial_result.completed_points == 4
    assert caught.value.partial_result.status == "failed"


def test_acquisition_and_persistence_failures_preserve_primary(
    config, tmp_path, monkeypatch
):
    import labtools.acquisition.hyperspectral as module

    def failed_save(*args, **kwargs):
        raise OSError("persistence-failed")

    monkeypatch.setattr(module, "save_hyperspectral_result", failed_save)
    with pytest.raises(HyperspectralAcquisitionError) as caught:
        run(
            HyperspectralService(Spectra(fail_at=2), mirrors()).acquire(
                config, output_path=tmp_path / "partial.npz"
            )
        )
    assert isinstance(caught.value.__cause__, OSError)
    assert str(caught.value.__cause__) == "spectrum-2"
    assert any("persistence failed" in note for note in caught.value.__notes__)
    assert caught.value.partial_result.completed_points == 1


def test_clean_persistence_failure_is_visible(config, tmp_path, monkeypatch):
    import labtools.acquisition.hyperspectral as module

    def failed_save(*args, **kwargs):
        raise OSError("persistence-failed")

    monkeypatch.setattr(module, "save_hyperspectral_result", failed_save)
    with pytest.raises(OSError, match="persistence-failed"):
        run(
            HyperspectralService(Spectra(), mirrors()).acquire(
                config, output_path=tmp_path / "complete.npz"
            )
        )


def test_system_exit_is_not_wrapped(config):
    class ExitSpectra(Spectra):
        async def acquire(self, settings, **kwargs):
            raise SystemExit(7)

    with pytest.raises(SystemExit) as caught:
        run(HyperspectralService(ExitSpectra(), mirrors()).acquire(config))
    assert caught.value.code == 7


def test_runtime_module_import_isolation_in_fresh_process():
    import subprocess
    import sys

    code = """
import sys
import labtools.runtime.hyperspectral
blocked = [name for name in sys.modules if name.startswith(
    ('PyQt', 'labtools.devices', 'horiba_sdk', 'u6', 'pylablib')
)]
assert not blocked, blocked
"""
    subprocess.run([sys.executable, "-c", code], check=True)
