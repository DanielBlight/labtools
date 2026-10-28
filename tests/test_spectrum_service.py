"""Offline service/adapter contracts; fake hardware is not hardware validation."""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from labtools.acquisition.spectrum_service import DarkRecord, SpectrumService
from labtools.config.spectrum import SpectrumSettings
from labtools.io.spectrum_records import (
    load_dark_record,
    save_dark_record,
    save_spectrum_result,
)
from labtools.runtime.spectrum_backend import create_spectrum_service, open_real_range


@pytest.fixture
def settings():
    return SpectrumSettings(
        "test-context-v1",
        "syncerity",
        0.1,
        2,
        0,
        0.5,
        500.0,
        600.0,
        backend="simulation",
    )


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize(
    "change",
    [
        {"exposure_s": float("nan")},
        {"exposure_s": 0},
        {"exposure_s": True},
        {"slit_width_mm": -1},
        {"end_nm": 500.0},
        {"start_nm": -1},
        {"configuration_id": ""},
        {"gain": True},
        {"speed": -1},
        {"overlap_pixels": -1},
        {"n_frames": 0},
        {"combine_mode": "unknown"},
        {"combine_mode": "median", "n_frames": 2},
        {"combine_mode": "sigma_clip", "n_frames": 2},
        {"n_frames": 2},
        {"backend": "auto"},
        {"preset": "unknown"},
    ],
)
def test_invalid_before_factory(settings, change):
    def forbidden(_):
        pytest.fail("must not create backend")

    with pytest.raises(ValueError):
        run(SpectrumService(forbidden).acquire(replace(settings, **change)))


@pytest.mark.parametrize("mode", ["none", "per_center", "per_frame", "pre_taken"])
def test_shared_service_synthetic_modes(settings, mode):
    service = create_spectrum_service(backend="simulation")
    dark = run(service.capture_dark(settings))
    result = run(
        service.acquire(
            settings, dark_mode=mode, dark=dark if mode == "pre_taken" else None
        )
    )
    assert result.settings.backend == "simulation"
    assert result.wavelength_nm.shape == (64,)
    assert np.isfinite(result.intensity).all()
    if mode == "pre_taken":
        np.testing.assert_allclose(
            result.raw_intensity - dark.intensity, result.intensity
        )
        assert result.dark_record_id == dark.record_id
    elif mode == "none":
        np.testing.assert_array_equal(result.raw_intensity, result.intensity)
    else:
        assert result.raw_intensity is None
        fresh = run(service.acquire(settings, dark_mode="pre_taken", dark=dark))
        np.testing.assert_allclose(result.intensity, fresh.intensity)


@pytest.mark.parametrize(
    "change",
    [
        {"configuration_id": "changed"},
        {"preset": "symphony"},
        {"exposure_s": 0.2},
        {"gain": 1},
        {"speed": 1},
        {"slit_width_mm": 0.2},
        {"start_nm": 501.0},
        {"end_nm": 601.0},
        {"overlap_pixels": 21},
        {"n_frames": 3, "combine_mode": "median"},
        {"backend": "real"},
    ],
)
def test_dark_mismatch_before_open(settings, change):
    dark = run(create_spectrum_service(backend="simulation").capture_dark(settings))

    def forbidden(_):
        pytest.fail("must reject before hardware opens")

    with pytest.raises(ValueError, match="settings differ"):
        run(
            SpectrumService(forbidden).acquire(
                replace(settings, **change), dark_mode="pre_taken", dark=dark
            )
        )


def test_dark_owned_immutable(settings):
    source = np.array([1.0, 2.0])
    dark = DarkRecord(settings, source, source, "test", "2026-10-27T00:00:00+00:00")
    source[:] = 9
    np.testing.assert_array_equal(dark.intensity, [1, 2])
    with pytest.raises(ValueError):
        dark.intensity[0] = 8
    with pytest.raises(ValueError):
        dark.intensity.setflags(write=True)


@pytest.mark.parametrize("bad_axis", [np.array([500.0]), np.array([500.0, 602.0])])
def test_axis_mismatch_still_closes(settings, bad_axis):
    events = []
    dark = DarkRecord(
        settings, [500.0, 600.0], [1.0, 2.0], "test", "2026-10-27T00:00:00+00:00"
    )

    @asynccontextmanager
    async def factory(_):
        async def acquire(mode):
            return bad_axis, np.ones(bad_axis.shape)

        try:
            yield SimpleNamespace(acquire=acquire)
        finally:
            events.append("close")

    with pytest.raises(ValueError, match="wavelength"):
        run(
            SpectrumService(factory).acquire(settings, dark_mode="pre_taken", dark=dark)
        )
    assert events == ["close"]


@pytest.mark.parametrize("when", ["before", "after", "error"])
def test_cancellation_and_error_cleanup(settings, when):
    events = []

    @asynccontextmanager
    async def factory(_):
        events.append("open")

        async def acquire(mode):
            events.append("acquire")
            if when == "error":
                raise OSError("capture failed")
            return [500.0, 600.0], [1.0, 2.0]

        try:
            yield SimpleNamespace(acquire=acquire)
        finally:
            events.append("close")

    cancel = lambda: when == "before" or (when == "after" and "acquire" in events)
    with pytest.raises(OSError if when == "error" else asyncio.CancelledError):
        run(SpectrumService(factory).acquire(settings, cancel_requested=cancel))
    assert events == ([] if when == "before" else ["open", "acquire", "close"])


def test_archive_roundtrip_and_no_overwrite(settings, tmp_path):
    service = create_spectrum_service(backend="simulation")
    dark = run(service.capture_dark(settings))
    path = tmp_path / "dark.npz"
    save_dark_record(path, dark)
    loaded = load_dark_record(path)
    assert loaded.settings == settings and loaded.record_id == dark.record_id
    np.testing.assert_array_equal(loaded.intensity, dark.intensity)
    with pytest.raises(FileExistsError):
        save_dark_record(path, dark)
    result = run(service.acquire(settings, dark_mode="pre_taken", dark=loaded))
    save_spectrum_result(tmp_path / "result.npz", result)
    with np.load(tmp_path / "result.npz", allow_pickle=False) as data:
        meta = json.loads(data["metadata"].item())
        assert meta["synthetic_data"] is True and meta["raw_available"] is True
        assert meta["dark_record_id"] == dark.record_id
        np.testing.assert_array_equal(data["raw_intensity"], result.raw_intensity)


@pytest.mark.parametrize("mode", ["per_center", "per_frame"])
def test_archive_does_not_invent_raw(settings, tmp_path, mode):
    result = run(
        create_spectrum_service(backend="simulation").acquire(settings, dark_mode=mode)
    )
    path = tmp_path / "result.npz"
    save_spectrum_result(path, result)
    with np.load(path, allow_pickle=False) as data:
        assert "raw_intensity" not in data.files
        assert json.loads(data["metadata"].item())["raw_available"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("synthetic_data", False),
        ("kind", "spectrum"),
    ],
)
def test_archive_rejects_bad_metadata(settings, tmp_path, field, value):
    dark = run(create_spectrum_service(backend="simulation").capture_dark(settings))
    path = tmp_path / "dark.npz"
    save_dark_record(path, dark)
    with np.load(path, allow_pickle=False) as data:
        meta = json.loads(data["metadata"].item())
        x, y = data["wavelength_nm"].copy(), data["intensity"].copy()
    meta[field] = value
    np.savez(path, metadata=json.dumps(meta), wavelength_nm=x, intensity=y)
    with pytest.raises(ValueError):
        load_dark_record(path)


@pytest.mark.parametrize(
    "failure", [None, "connect", "configure", "capture", "disconnect", "both"]
)
def test_real_adapter_fake_lifecycle_one_loop(settings, monkeypatch, failure):
    from labtools.acquisition import range_spectrum

    events, loops = [], []

    def event(name):
        events.append(name)
        loops.append(asyncio.get_running_loop())
        if name == failure or (failure == "both" and name in {"capture", "disconnect"}):
            raise OSError(name)

    class Fake:
        def __init__(self, **kw):
            assert kw == {"preset": "syncerity"}

        async def connect(self):
            event("connect")

        async def configure(self, **kw):
            event("configure")
            assert kw == {
                "gain": 2, "speed": 0, "exposure_time": 0.1, "roi": None, "entrance_slit_width_mm": 0.5
            }

        async def disconnect(self):
            event("disconnect")

    async def capture(spec, start, end, **kw):
        event("capture")
        assert (start, end) == (500.0, 600.0)
        assert kw == {
            "stitch_pixel_overlap": 20, "n_frames": 1, "mode": "single", "dark_mode": "none"
        }
        return np.array([500.0, 600.0]), np.array([1.0, 2.0])

    monkeypatch.setattr(range_spectrum, "get_range_spectrum", capture)

    @asynccontextmanager
    async def factory(c):
        async with open_real_range(c, spectrometer_factory=Fake) as backend:
            yield backend

    service = SpectrumService(factory)
    if failure:
        with pytest.raises(OSError) as caught:
            run(service.acquire(replace(settings, backend="real")))
        if failure == "both":
            assert str(caught.value) == "capture"
            assert "disconnect" in caught.value.__notes__[0]
    else:
        assert (
            run(service.acquire(replace(settings, backend="real"))).raw_intensity
            is not None
        )
    assert events[-1] == "disconnect"
    assert all(loop is loops[0] for loop in loops)


def test_no_fallback_or_unverified_dark(settings):
    service = create_spectrum_service(backend="simulation")
    with pytest.raises(ValueError, match="provenance"):
        run(service.acquire(settings, dark_mode="pre_taken"))
    with pytest.raises(ValueError, match="refuses real"):
        run(service.acquire(replace(settings, backend="real")))
    with pytest.raises(ValueError):
        create_spectrum_service(backend="auto")


def test_import_isolation(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    code = """
import importlib.abc, sys, asyncio
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('labtools.devices', 'horiba_sdk', 'PyQt6', 'u6', 'pyvisa')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from labtools.runtime.spectrum_backend import create_spectrum_service
from labtools.config.spectrum import SpectrumSettings
s = SpectrumSettings('toy', 'syncerity', .1, 2, 0, .5, 500., 600., backend='simulation')
assert asyncio.run(create_spectrum_service(backend='simulation').acquire(s)).intensity.size == 64
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_failed_archive_write_removes_partial_file(settings, tmp_path, monkeypatch):
    dark = run(create_spectrum_service(backend="simulation").capture_dark(settings))
    path = tmp_path / "dark.npz"

    def fail(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(np, "savez_compressed", fail)
    with pytest.raises(OSError):
        save_dark_record(path, dark)
    assert not path.exists()


def test_dark_archive_missing_setting_is_not_defaulted(settings, tmp_path):
    dark = run(create_spectrum_service(backend="simulation").capture_dark(settings))
    path = tmp_path / "dark.npz"
    save_dark_record(path, dark)
    with np.load(path, allow_pickle=False) as data:
        meta = json.loads(data["metadata"].item())
        x, y = data["wavelength_nm"].copy(), data["intensity"].copy()
    del meta["settings"]["overlap_pixels"]
    np.savez(path, metadata=json.dumps(meta), wavelength_nm=x, intensity=y)
    with pytest.raises(ValueError, match="every settings field"):
        load_dark_record(path)


def test_real_dark_adapter_delegates_existing_range_capture(settings, monkeypatch):
    from labtools.acquisition import range_spectrum
    from labtools.processing.dark_spectrum import DarkSpectrum

    calls = []

    class Fake:
        def __init__(self, **kwargs):
            pass

        async def connect(self):
            calls.append("connect")

        async def configure(self, **kwargs):
            calls.append("configure")

        async def disconnect(self):
            calls.append("disconnect")

    async def capture(spec, start, end, **kwargs):
        calls.append("dark")
        assert kwargs == {"stitch_pixel_overlap": 20, "n_frames": 1, "mode": "single"}
        return DarkSpectrum(np.array([500.0, 600.0]), np.array([1.0, 2.0]))

    monkeypatch.setattr(range_spectrum, "capture_range_dark", capture)

    @asynccontextmanager
    async def factory(c):
        async with open_real_range(c, spectrometer_factory=Fake) as backend:
            yield backend

    dark = run(SpectrumService(factory).capture_dark(replace(settings, backend="real")))
    assert dark.settings.backend == "real"
    assert calls == ["connect", "configure", "dark", "disconnect"]
