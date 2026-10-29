from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import replace

import numpy as np
import pytest

from labtools.acquisition.hyperspectral import (
    HyperspectralService,
    load_hyperspectral_result,
    save_hyperspectral_result,
)
from labtools.config.hyperspectral import HyperspectralConfig
from labtools.config.spectrum import SpectrumSettings
from labtools.runtime.spectrum_backend import create_spectrum_service
from labtools.simulation.hyperspectral import open_simulated_hyperspectral_mirror


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def config():
    spectrum = SpectrumSettings(
        "hyperspectral-test-spectrum-v1",
        "syncerity",
        0.1,
        2,
        0,
        0.5,
        500.0,
        600.0,
        backend="simulation",
    )
    return HyperspectralConfig(
        "hyperspectral-test-v1",
        spectrum,
        -0.1,
        0.1,
        3,
        -0.2,
        0.2,
        2,
    )


def service():
    return HyperspectralService(
        create_spectrum_service(backend="simulation"),
        open_simulated_hyperspectral_mirror,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"configuration_id": ""},
        {"x_points": 0},
        {"y_points": True},
        {"settle_time_s": -1},
        {"backend": "real"},
        {"dark_mode": "bad"},
    ],
)
def test_validation(config, change):
    with pytest.raises(ValueError):
        run(service().acquire(replace(config, **change)))


def test_deterministic_dimensions_axes_progress_and_provenance(config):
    events = []
    first = run(service().acquire(config, progress=events.append))
    second = run(service().acquire(config))
    assert first.status == "complete"
    assert first.intensity.shape == (2, 3, 64)
    assert np.array_equal(first.x_v, np.linspace(-0.1, 0.1, 3))
    assert np.array_equal(first.y_v, np.linspace(-0.2, 0.2, 2))
    assert np.array_equal(first.intensity, second.intensity)
    assert first.provenance.synthetic is True
    assert first.provenance.scan_order == "y-major/x-minor"
    assert first.provenance.simulation_model_id
    assert [event.phase for event in events].count("point_completed") == 6
    assert not first.intensity.flags.writeable


def test_cooperative_cancellation_preserves_partial_output(config, tmp_path):
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls > 3

    path = tmp_path / "partial.npz"
    result = run(service().acquire(config, cancel_requested=cancel, output_path=path))
    assert result.status == "cancelled"
    assert 0 < result.completed_points < 6
    restored = load_hyperspectral_result(path)
    assert restored.status == "cancelled"
    assert np.array_equal(restored.completed_mask, result.completed_mask)
    assert np.isnan(restored.intensity[~restored.completed_mask]).all()


def test_persistence_round_trip_and_overwrite_refusal(config, tmp_path):
    value = run(service().acquire(config))
    path = tmp_path / "cube.npz"
    save_hyperspectral_result(value, path)
    restored = load_hyperspectral_result(path)
    assert np.array_equal(restored.intensity, value.intensity)
    with pytest.raises(FileExistsError):
        save_hyperspectral_result(value, path)


def test_backend_identity_mismatch(config):
    async def real_factory():
        raise AssertionError

    class Bad:
        backend_identity = "real:test"

        async def move_to(self, x_v, y_v):
            pass

        async def home(self):
            pass

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def bad_factory():
        yield Bad()

    with pytest.raises(ValueError, match="backend identity"):
        run(
            HyperspectralService(
                create_spectrum_service(backend="simulation"), bad_factory
            ).acquire(config)
        )


def test_borrowed_and_owned_service_close(config):
    class ClosingSpectra:
        closed = 0

        async def acquire(self, settings, **kwargs):
            return await create_spectrum_service(backend="simulation").acquire(settings)

        async def close(self):
            self.closed += 1

    borrowed = ClosingSpectra()
    owned = ClosingSpectra()

    async def exercise():
        async with HyperspectralService(borrowed, open_simulated_hyperspectral_mirror):
            pass
        async with HyperspectralService(
            owned, open_simulated_hyperspectral_mirror, owns_spectrum_service=True
        ):
            pass

    run(exercise())
    assert borrowed.closed == 0
    assert owned.closed == 1


def test_clean_process_import_isolation():
    code = """
import sys
import labtools.config.hyperspectral
import labtools.acquisition.hyperspectral
import labtools.simulation.hyperspectral
blocked = [n for n in sys.modules if n.startswith(('PyQt', 'labtools.devices', 'horiba_sdk', 'u6'))]
assert not blocked, blocked
"""
    subprocess.run([sys.executable, "-c", code], check=True)
