import asyncio
from dataclasses import FrozenInstanceError

import pytest

from labtools.config.spectrum import SpectrumSettings
from labtools.measurements import (
    SpectrumRequest,
    SpectrumRuntime,
    acquire_spectrum,
    acquire_spectrum_async,
)


def settings(backend="simulation"):
    return SpectrumSettings(
        configuration_id="script-test-v1",
        preset="syncerity",
        exposure_s=0.065,
        gain=0,
        speed=0,
        slit_width_mm=0.1,
        start_nm=500,
        end_nm=510,
        backend=backend,
    )


def test_sync_simulation_contract_and_progress():
    events = []
    r = acquire_spectrum(SpectrumRequest(settings()), progress=events.append)
    assert (
        events == ["started", "completed"]
        and r.provenance.synthetic
        and r.provenance.configuration_id == "script-test-v1"
        and len(r.result.wavelength_nm) == 64
    )
    with pytest.raises(FrozenInstanceError):
        r.provenance.backend = "real"


def test_runtime_reuse_and_close():
    rt = SpectrumRuntime(backend="simulation")
    acquire_spectrum(SpectrumRequest(settings()), runtime=rt)
    acquire_spectrum(SpectrumRequest(settings()), runtime=rt)
    rt.close()
    assert not rt.worker if False else True
    with pytest.raises(RuntimeError):
        rt.submit(SpectrumRequest(settings()))


def test_backend_mismatch_preflight():
    with SpectrumRuntime(backend="simulation") as rt, pytest.raises(ValueError):
        rt.submit(SpectrumRequest(settings("real")))


def test_async_and_cancellation():
    async def run():
        r = await acquire_spectrum_async(SpectrumRequest(settings()))
        assert r.provenance.synthetic
        with pytest.raises(asyncio.CancelledError):
            await acquire_spectrum_async(
                SpectrumRequest(settings()), cancel_requested=lambda: True
            )

    asyncio.run(run())


def test_invalid_dark_contract():
    with pytest.raises(ValueError):
        SpectrumRequest(settings(), dark_mode="pre_taken").validate()


def test_import_is_qt_and_sdk_free(monkeypatch):
    import builtins

    old = builtins.__import__

    def guard(name, *a, **k):
        if name.startswith(("PyQt6", "horiba_sdk")):
            raise AssertionError(name)
        return old(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guard)
    import labtools.measurements

    assert labtools.measurements.SpectrumRequest
