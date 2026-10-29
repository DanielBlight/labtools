from __future__ import annotations

import subprocess
import sys
from dataclasses import replace

import pytest

from labtools import measurements
from labtools.config.hyperspectral import HyperspectralConfig
from labtools.config.spectrum import SpectrumSettings
from labtools.measurements.hyperspectral import (
    HyperspectralRequest,
    HyperspectralRuntime,
)

PUBLIC = {
    "HyperspectralMeasurement",
    "HyperspectralMeasurementProvenance",
    "HyperspectralRequest",
    "HyperspectralRuntime",
    "acquire_hyperspectral_map",
    "acquire_hyperspectral_map_async",
}


def config(backend="simulation"):
    settings = SpectrumSettings(
        "public-contract-spectrum-v1",
        "syncerity",
        0.1,
        2,
        0,
        0.5,
        500.0,
        600.0,
        backend=backend,
    )
    return HyperspectralConfig(
        "public-contract-v1",
        settings,
        0.0,
        0.1,
        2,
        0.0,
        0.1,
        2,
        backend=backend,
    )


def test_exact_additive_exports_and_no_internal_exports():
    assert PUBLIC <= set(measurements.__all__)
    assert not {"HyperspectralService", "HyperspectralMirrorProvider"} & set(
        measurements.__all__
    )


@pytest.mark.parametrize("owner", ["", "   "])
def test_blank_owner_rejected_before_runtime(owner):
    with pytest.raises(ValueError, match="owner"):
        HyperspectralRequest(config(), owner=owner).validate()


def test_output_path_type_and_existing_path_rejected(tmp_path):
    with pytest.raises(ValueError, match="pathlib.Path"):
        HyperspectralRequest(config(), output_path="cube.npz").validate()
    path = tmp_path / "cube.npz"
    path.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        HyperspectralRequest(config(), output_path=path).validate()


def test_backend_mismatch_rejected():
    with pytest.raises(ValueError, match="backends must match"):
        replace(config(), backend="real").validate()


def test_runtime_owned_cleanup_attempts_all_and_preserves_interrupt():
    events = []

    class Resource:
        def __init__(self, name, error):
            self.name, self.error = name, error

        def close(self):
            events.append(self.name)
            raise self.error

    runtime = HyperspectralRuntime(
        backend="simulation",
        spectrum_service=Resource("spectrum", KeyboardInterrupt()),
        session=Resource("session", RuntimeError("session-close")),
        owns_spectrum_service=True,
        owns_session=True,
    )
    with pytest.raises(KeyboardInterrupt) as caught:
        runtime.close()
    assert events == ["spectrum", "session"]
    assert any(
        "Additional hyperspectral cleanup" in note for note in caught.value.__notes__
    )
    runtime.close()


def test_runtime_borrowed_resources_are_not_closed():
    class Resource:
        closed = 0

        def close(self):
            self.closed += 1

    service, session = Resource(), Resource()
    runtime = HyperspectralRuntime(
        backend="simulation",
        spectrum_service=service,
        session=session,
    )
    runtime.close()
    runtime.close()
    assert service.closed == session.closed == 0


def test_cancelled_partial_not_replaced_on_operation_exit():
    checks = 0

    def cancel():
        nonlocal checks
        checks += 1
        return checks > 5

    result = measurements.acquire_hyperspectral_map(
        HyperspectralRequest(config()), cancel_requested=cancel
    )
    assert result.result.status == "cancelled"
    assert result.result.completed_points > 0


def test_fresh_process_public_import_is_native_free(tmp_path):
    code = """
import os, sys
os.chdir(sys.argv[1])
import labtools.measurements
import labtools.measurements.hyperspectral
import labtools.measurements.recipes
import labtools.measurements.dispatch
blocked = [n for n in sys.modules if n.startswith(
 ('PyQt', 'labtools.devices', 'horiba_sdk', 'u6', 'pylablib.devices'))]
assert not blocked, blocked
assert not list(__import__('pathlib').Path('.').iterdir())
"""
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=True)
