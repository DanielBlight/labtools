import asyncio
from dataclasses import replace

import pytest

from labtools.config.spectrum import SpectrumSettings
from labtools.measurements import (
    SpectrumRequest,
    acquire_spectrum,
    capture_dark,
    capture_dark_async,
    load_dark,
    request_with_dark,
    save_dark,
)


def settings():
    return SpectrumSettings(
        configuration_id="dark-script-v1",
        preset="syncerity",
        exposure_s=0.065,
        gain=0,
        speed=0,
        slit_width_mm=0.1,
        start_nm=500,
        end_nm=510,
        backend="simulation",
    )


def test_capture_save_load_reuse(tmp_path):
    events = []
    dark = capture_dark(SpectrumRequest(settings()), progress=events.append)
    assert events == ["started", "completed"] and not dark.intensity.flags.writeable
    p = tmp_path / "dark.npz"
    save_dark(p, dark)
    loaded = load_dark(p)
    assert loaded.settings == dark.settings and loaded.record_id == dark.record_id
    result = acquire_spectrum(request_with_dark(settings(), loaded))
    assert (
        result.result.dark_record_id == loaded.record_id
        and result.result.dark_mode == "pre_taken"
    )


def test_mismatch_before_acquisition():
    d = capture_dark(SpectrumRequest(settings()))
    with pytest.raises(ValueError):
        request_with_dark(replace(settings(), configuration_id="other"), d)


def test_async_capture_and_cancel():
    async def run():
        d = await capture_dark_async(SpectrumRequest(settings()))
        assert d.settings == settings()
        with pytest.raises(asyncio.CancelledError):
            await capture_dark_async(
                SpectrumRequest(settings()), cancel_requested=lambda: True
            )

    asyncio.run(run())


def test_npz_refuses_overwrite(tmp_path):
    d = capture_dark(SpectrumRequest(settings()))
    p = tmp_path / "d.npz"
    save_dark(p, d)
    with pytest.raises(FileExistsError):
        save_dark(p, d)


def test_arrays_immutable():
    d = capture_dark(SpectrumRequest(settings()))
    with pytest.raises(ValueError):
        d.intensity[0] = 2
