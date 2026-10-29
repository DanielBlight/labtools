import builtins

import pytest

from labtools.measurements import MeasurementRuntime


class R:
    def __init__(self, backend="simulation", fail=None):
        self.backend = backend
        self.fail = fail
        self.closed = 0

    def close(self):
        self.closed += 1
        if self.fail:
            raise self.fail


def test_lazy_and_owned_cleanup():
    created = []

    def f(**k):
        r = R(**k)
        created.append(r)
        return r

    rt = MeasurementRuntime(backend="simulation", spectrum_factory=f, map_factory=f)
    assert not rt.status().spectrum_created
    assert rt.spectrum is rt.spectrum and rt.intensity_map
    rt.close()
    assert [x.closed for x in created] == [1, 1]
    rt.close()


def test_borrowed_not_closed():
    a, b = R(), R()
    with MeasurementRuntime(backend="simulation", spectrum_runtime=a, map_runtime=b):
        pass
    assert (a.closed, b.closed) == (0, 0)


def test_backend_mismatch():
    with pytest.raises(ValueError):
        MeasurementRuntime(backend="simulation", spectrum_runtime=R("real"))


def test_cleanup_aggregates_and_closes_both():
    a, b = R(fail=OSError("a")), R(fail=ValueError("b"))
    rt = MeasurementRuntime(
        backend="simulation", spectrum_factory=lambda **_: a, map_factory=lambda **_: b
    )
    assert rt.spectrum is a
    assert rt.intensity_map is b
    with pytest.raises(ExceptionGroup) as e:
        rt.close()
    assert len(e.value.exceptions) == 2 and a.closed == b.closed == 1


def test_body_primary_preserved():
    primary = RuntimeError("body")
    with (
        pytest.raises(RuntimeError) as e,
        MeasurementRuntime(
            backend="simulation", spectrum_factory=lambda **_: R(fail=OSError())
        ) as rt,
    ):
        assert rt.spectrum is not None
        raise primary
    assert e.value is primary and e.value.__notes__


def test_import_is_qt_native_free(monkeypatch):
    old = builtins.__import__

    def guard(name, *a, **k):
        if name.startswith(("PyQt6", "horiba_sdk", "u6", "pyvisa", "zmq")):
            raise AssertionError(name)
        return old(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guard)
    from labtools.measurements import runtime

    assert runtime.MeasurementRuntime


def test_sequential_simulation_contract(tmp_path):
    from labtools.config.intensity_map import IntensityMapConfig
    from labtools.config.spectrum import SpectrumSettings
    from labtools.measurements import (
        IntensityMapRequest,
        SpectrumRequest,
        acquire_intensity_map,
        acquire_spectrum,
    )

    with MeasurementRuntime(backend="simulation") as rt:
        s = SpectrumSettings(
            configuration_id="runtime-v1",
            preset="syncerity",
            exposure_s=0.065,
            gain=0,
            speed=0,
            slit_width_mm=0.1,
            start_nm=500,
            end_nm=510,
            backend="simulation",
        )
        assert acquire_spectrum(
            SpectrumRequest(s), runtime=rt.spectrum
        ).provenance.synthetic
        c = IntensityMapConfig(
            x_start_v=0,
            x_stop_v=0.1,
            x_points=2,
            y_start_v=0,
            y_stop_v=0.1,
            y_points=2,
            integration_time_s=0.001,
            channels=(1,),
            channel_thresholds_v=(0.1,),
            channel_edges=("rising",),
            backend="simulation",
            output_root=tmp_path,
            save_results=False,
        )
        assert acquire_intensity_map(
            IntensityMapRequest(c), runtime=rt.intensity_map
        ).result.complete
