import asyncio
from dataclasses import FrozenInstanceError

import pytest

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.measurements import (
    AlignmentRequest,
    SpectrumRuntime,
    acquire_alignment_frame,
    acquire_alignment_frame_async,
)


def settings():
    return AlignmentSettings(
        "alignment-script-v1", backend="simulation", exposure_s=0.065
    )


def test_sync_provenance_progress():
    e = []
    m = acquire_alignment_frame(AlignmentRequest(settings()), progress=e.append)
    assert (
        e == ["started", "completed"]
        and m.provenance.synthetic
        and len(m.result.wavelength_nm) == 64
    )
    with pytest.raises(FrozenInstanceError):
        m.provenance.backend = "real"


def test_runtime_reuse():
    with SpectrumRuntime(backend="simulation") as r:
        acquire_alignment_frame(AlignmentRequest(settings()), runtime=r)
        acquire_alignment_frame(AlignmentRequest(settings()), runtime=r)


def test_async_and_cancel():
    async def run():
        assert (
            await acquire_alignment_frame_async(AlignmentRequest(settings()))
        ).provenance.synthetic
        with pytest.raises(asyncio.CancelledError):
            await acquire_alignment_frame_async(
                AlignmentRequest(settings()), cancel_requested=lambda: True
            )

    asyncio.run(run())


def test_backend_mismatch():
    with SpectrumRuntime(backend="simulation") as r, pytest.raises(ValueError):
        acquire_alignment_frame(
            AlignmentRequest(AlignmentSettings("x", backend="real")), runtime=r
        )


def test_owner_validation():
    with pytest.raises(ValueError):
        AlignmentRequest(settings(), owner=" ").validate()
