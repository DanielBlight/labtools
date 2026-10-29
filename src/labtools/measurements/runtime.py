"""Qt-free owner composition for sequential scripted measurements."""

from __future__ import annotations

from dataclasses import dataclass

from .intensity_map import IntensityMapRuntime
from .spectrum import SpectrumRuntime


@dataclass(frozen=True)
class MeasurementRuntimeStatus:
    backend: str
    closed: bool
    spectrum_created: bool
    map_created: bool


class MeasurementRuntime:
    """Lazily compose spectrum and map runtimes without merging ownership models."""

    def __init__(
        self,
        *,
        backend: str,
        spectrum_runtime=None,
        map_runtime=None,
        spectrum_factory=SpectrumRuntime,
        map_factory=IntensityMapRuntime,
    ) -> None:
        if backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        for name, value in (("spectrum", spectrum_runtime), ("map", map_runtime)):
            if value is not None and value.backend != backend:
                raise ValueError(f"{name} runtime backend does not match")
        self.backend = backend
        self._spectrum = spectrum_runtime
        self._map = map_runtime
        self._spectrum_factory = spectrum_factory
        self._map_factory = map_factory
        self._own_spectrum = spectrum_runtime is None
        self._own_map = map_runtime is None
        self._closed = False

    def _check(self):
        if self._closed:
            raise RuntimeError("MeasurementRuntime is closed")

    @property
    def spectrum(self):
        self._check()
        if self._spectrum is None:
            self._spectrum = self._spectrum_factory(backend=self.backend)
        return self._spectrum

    @property
    def intensity_map(self):
        self._check()
        if self._map is None:
            self._map = self._map_factory(backend=self.backend)
        return self._map

    def status(self):
        return MeasurementRuntimeStatus(
            self.backend,
            self._closed,
            self._spectrum is not None,
            self._map is not None,
        )

    def close(self):
        if self._closed:
            return
        failures = []
        for runtime, owned in (
            (self._spectrum, self._own_spectrum),
            (self._map, self._own_map),
        ):
            if runtime is not None and owned:
                try:
                    runtime.close()
                except BaseException as exc:  # noqa: BLE001 - attempt all owned cleanup
                    failures.append(exc)
        self._closed = True
        if failures:
            primary = next((e for e in failures if not isinstance(e, Exception)), None)
            if primary is not None:
                for e in failures:
                    if e is not primary:
                        primary.add_note(f"Additional runtime cleanup failed: {e!r}")
                raise primary
            raise ExceptionGroup("Measurement runtime cleanup failed", failures)

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, typ, value, tb):
        try:
            self.close()
        except BaseException as cleanup:
            if value is None:
                raise
            value.add_note(f"Measurement runtime cleanup also failed: {cleanup!r}")
