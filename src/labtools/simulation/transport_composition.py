"""Compose both existing native-contract boundaries with fixed fake transports.

External requests/results stay simulation-labelled, including all saved provenance.
Only internal provider settings use real-contract labels; no native factory is loaded.
"""

from contextlib import asynccontextmanager
from dataclasses import replace

from labtools.acquisition.intensity_map import acquire_intensity_map
from labtools.acquisition.spectrum_service import SpectrumService
from labtools.runtime.workspace_map_transport import WorkspaceMapTransport
from labtools.runtime.workspace_spectrum_transport import WorkspaceSpectrumTransport
from labtools.simulation.transport_fakes import (
    TransportTrace,
    map_factories,
    single_capture_stitch,
    spectrum_factory,
)


class FakeTransportComposition:
    def __init__(self):
        self.trace = TransportTrace()
        self._ownership = None
        self.spectrum = SpectrumService(self._spectrum_backend)

    def bind(self, ownership):
        if self._ownership is not None:
            raise RuntimeError("Composition already bound")
        ownership.config.validate()
        self._ownership = ownership

    def _require_bound(self):
        if self._ownership is None:
            raise RuntimeError("Bind composition before starting a workflow")

    def acquire_map(self, config, **kwargs):
        self._require_bound()
        if config.backend != "simulation":
            raise ValueError("Fake composition accepts simulation requests only")
        if "device_provider" in kwargs:
            raise ValueError("Fake composition owns the provider")
        boundary = WorkspaceMapTransport(
            ownership=self._ownership,
            configuration_id=self._ownership.config.configuration_id,
            factories=map_factories(config, self.trace),
        )
        contract = replace(config, backend="real")
        # Check ownership before acquisition creates an output directory.
        boundary._require_reservation(contract)
        return acquire_intensity_map(
            config, device_provider=lambda _config: boundary._backend(contract), **kwargs,
        )

    @asynccontextmanager
    async def _spectrum_backend(self, settings):
        self._require_bound()
        if settings.backend != "simulation":
            raise ValueError("Fake composition accepts simulation requests only")
        boundary = WorkspaceSpectrumTransport(
            ownership=self._ownership,
            spectrometer_factory=spectrum_factory(settings, self.trace),
            stitcher=single_capture_stitch,
        )
        async with boundary._backend(replace(settings, backend="real")) as backend:
            yield backend


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


def rehearse_composition(output_root, config):
    """Run the complete composition without Qt, recording synthetic outputs only."""
    import asyncio
    import json
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    import numpy as np

    from labtools.config.intensity_map import IntensityMapConfig
    from labtools.config.spectrum import SpectrumSettings
    from labtools.io.spectrum_records import (
        load_dark_record,
        save_dark_record,
        save_spectrum_result,
    )
    from labtools.runtime.session import ResourceBusyError
    from labtools.simulation.ownership import WorkspaceOwnership

    config.validate()
    root = Path(output_root).expanduser().resolve() / "SIMULATION"
    root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="transport-rehearsal-", dir=root))
    (output / "SYNTHETIC_DATA.txt").write_text("FAKE TRANSPORTS ONLY - not experimental data\n", encoding="utf-8")
    report = {"status": "running", "synthetic_data": True, "configuration_id": config.configuration_id,
              "output_directory": str(output), "checks": {},
              "limitations": "Fake transports and one-centre stitcher; no SDK or connected-device acceptance"}
    services = FakeTransportComposition()
    ownership = WorkspaceOwnership(config)
    try:
        services.bind(ownership)
        mapping = IntensityMapConfig(
            -1, 1, 3, -1, 1, 3, backend="simulation", simulation_seed=config.simulation_seed,
            simulation_realtime=False, settle_time_s=0, integration_time_s=.001,
            output_root=output / "Maps", save_results=True,
        )
        spectrum = SpectrumSettings(
            configuration_id=config.configuration_id, backend="simulation", preset="syncerity",
            exposure_s=.065, gain=0, speed=0, slit_width_mm=.1, start_nm=500, end_nm=600,
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            with ownership.reserve("Intensity map"):
                complete = executor.submit(services.acquire_map, mapping).result()
                _check(complete.complete, "Map did not complete")
                report["checks"]["map_complete"] = True
                shared = bool(set(config.map_resources) & set(config.spectrum_resources))
                if shared:
                    try:
                        ownership.reserve("Spectrum")
                    except ResourceBusyError:
                        report["checks"]["configured_conflict_policy"] = True
                    else:
                        raise AssertionError("Conflicting lease was granted")
                else:
                    with ownership.reserve("Spectrum"):
                        report["checks"]["configured_conflict_policy"] = True
            progress = [0]

            def update(snapshot):
                progress[0] = snapshot.points_complete

            with ownership.reserve("Intensity map"):
                stopped = executor.submit(
                    services.acquire_map, mapping, progress_callback=update,
                    cancel_requested=lambda: progress[0] >= 3,
                ).result()
                _check(not stopped.complete and stopped.completed_mask.sum() == 3, "Map did not stop at three points")
            with ownership.reserve("Intensity map"):
                resumed = executor.submit(
                    services.acquire_map, mapping, resume_directory=stopped.output_directory,
                ).result()
                np.testing.assert_array_equal(complete.counts, resumed.counts)
                _check(resumed.complete and resumed.resumed, "Map did not resume")
                report["checks"]["map_cancel_resume"] = True
            services.trace.fail_next("counter", "read")
            with ownership.reserve("Intensity map"):
                try:
                    executor.submit(services.acquire_map, mapping).result()
                except OSError as error:
                    _check("Injected fake counter" in str(error), "Unexpected map failure")
                else:
                    raise AssertionError("Map fault was not raised")
            with ownership.reserve("Intensity map"):
                _check(executor.submit(services.acquire_map, mapping).result().complete, "Map did not recover")
                report["checks"]["map_failure_recovery"] = True

            def run(coroutine):
                return executor.submit(asyncio.run, coroutine).result()

            with ownership.reserve("Spectrum"):
                raw = run(services.spectrum.acquire(spectrum))
                dark = run(services.spectrum.capture_dark(spectrum))
                save_dark_record(output / "dark.npz", dark)
                dark = load_dark_record(output / "dark.npz")
                corrected = run(services.spectrum.acquire(spectrum, dark_mode="pre_taken", dark=dark))
                np.testing.assert_allclose(raw.intensity - dark.intensity, corrected.intensity)
                repeated = run(services.spectrum.acquire(spectrum, dark_mode="pre_taken", dark=dark))
                np.testing.assert_array_equal(corrected.intensity, repeated.intensity)
                report["checks"]["spectrum_dark_archive_subtract_repeat"] = True
                try:
                    run(services.spectrum.acquire(spectrum, cancel_requested=lambda: True))
                except asyncio.CancelledError:
                    report["checks"]["spectrum_cancellation"] = True
                else:
                    raise AssertionError("Spectrum cancellation was not raised")
                services.trace.fail_next("spectrometer", "acquire")
                try:
                    run(services.spectrum.acquire(spectrum))
                except OSError:
                    pass
                else:
                    raise AssertionError("Spectrum fault was not raised")
                run(services.spectrum.acquire(spectrum))
                report["checks"]["spectrum_failure_recovery"] = True
            save_spectrum_result(output / "raw_spectrum.npz", raw)
            save_spectrum_result(output / "corrected_spectrum.npz", corrected)
            with np.load(output / "corrected_spectrum.npz", allow_pickle=False) as archive:
                metadata = json.loads(str(archive["metadata"].item()))
                _check(metadata["synthetic_data"] and metadata["settings"]["backend"] == "simulation", "Spectrum provenance is not synthetic")
            report["checks"]["synthetic_archive_provenance"] = True
            _check(not ownership.session.reservations(), "Workspace still has active leases")
            report["checks"]["all_leases_released"] = True
        events = services.trace.events()
        groups = {}
        for event in events:
            groups.setdefault(event["handle"], []).append(event)
        for group in groups.values():
            _check(len({(event["thread"], event["loop"]) for event in group}) == 1, "Handle affinity changed")
        report["checks"]["handle_affinity"] = True
        report["events"] = events
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        ownership.close()
        (output / "rehearsal.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
