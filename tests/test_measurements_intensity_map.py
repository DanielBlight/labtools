import asyncio
from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from labtools.config.intensity_map import SCHEMA_VERSION, IntensityMapConfig
from labtools.measurements import (
    IntensityMapRequest,
    IntensityMapRuntime,
    acquire_intensity_map,
    acquire_intensity_map_async,
    request_from_resume,
)


def config(tmp_path):
    return IntensityMapConfig(
        x_start_v=-0.1,
        x_stop_v=0.1,
        x_points=2,
        y_start_v=-0.1,
        y_stop_v=0.1,
        y_points=2,
        integration_time_s=0.001,
        channels=(1,),
        channel_thresholds_v=(0.1,),
        channel_edges=("rising",),
        backend="simulation",
        output_root=tmp_path,
        save_results=False,
        simulation_seed=42,
    )


def test_simulation_provenance_progress(tmp_path):
    p = []
    m = acquire_intensity_map(IntensityMapRequest(config(tmp_path)), progress=p.append)
    assert (
        m.result.complete
        and len(p) == 4
        and m.provenance.synthetic
        and m.provenance.schema_version == SCHEMA_VERSION
        and m.result.output_directory.is_dir()
    )
    with pytest.raises(FrozenInstanceError):
        m.provenance.backend = "real"


def test_stop_resume_deterministic(tmp_path):
    c = config(tmp_path)
    calls = [0]

    def stop():
        calls[0] += 1
        return calls[0] > 2

    partial = acquire_intensity_map(IntensityMapRequest(c), cancel_requested=stop)
    assert not partial.result.complete
    resumed = acquire_intensity_map(
        request_from_resume(partial.result.output_directory)
    )
    fresh = acquire_intensity_map(
        IntensityMapRequest(replace(c, output_root=tmp_path / "fresh"))
    )
    np.testing.assert_array_equal(resumed.result.counts, fresh.result.counts)
    assert resumed.result.resumed


def test_async(tmp_path):
    async def run():
        assert (
            await acquire_intensity_map_async(IntensityMapRequest(config(tmp_path)))
        ).result.complete

    asyncio.run(run())


def test_runtime_backend_mismatch(tmp_path):
    with IntensityMapRuntime(backend="simulation") as r, pytest.raises(ValueError):
        acquire_intensity_map(
            IntensityMapRequest(replace(config(tmp_path), backend="real")),
            runtime=r,
        )


def test_injected_provider_forwarded(tmp_path):
    seen = []

    def provider(c):
        seen.append(c)
        from labtools.runtime.map_devices import open_map_devices

        return open_map_devices(c)

    with IntensityMapRuntime(backend="simulation", device_provider=provider) as r:
        acquire_intensity_map(IntensityMapRequest(config(tmp_path)), runtime=r)
    assert len(seen) == 1
